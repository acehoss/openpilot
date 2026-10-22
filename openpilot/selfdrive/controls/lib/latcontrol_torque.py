import math
import numpy as np
from collections import deque

from openpilot.cereal import log
from opendbc.car.chrysler.values import SUSW_CARS
from opendbc.car.lateral import FRICTION_THRESHOLD, get_friction
from openpilot.common.constants import ACCELERATION_DUE_TO_GRAVITY
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.common.pid import PIDController

# At higher speeds (25+mph) we can assume:
# Lateral acceleration achieved by a specific car correlates to
# torque applied to the steering rack. It does not correlate to
# wheel slip, or to speed.

# This controller applies torque to achieve desired lateral
# accelerations. To compensate for the low speed effects the
# proportional gain is increased at low speeds by the PID controller.
# Additionally, there is friction in the steering wheel that needs
# to be overcome to move it at all, this is compensated for too.

KP = 0.8
KI = 0.15

INTERP_SPEEDS = [1, 1.5, 2.0, 3.0, 5, 7.5, 10, 15, 30]
KP_INTERP = [250, 120, 65, 30, 11.5, 5.5, 3.5, 2.0, KP]

LP_FILTER_CUTOFF_HZ = 1.2
JERK_LOOKAHEAD_SECONDS = 0.19
JERK_GAIN = 0.3
LAT_ACCEL_REQUEST_BUFFER_SECONDS = 1.0
VERSION = 1

# Fork: the SUSW column (Renegade) sticks and releases under the upstream KP schedule. Hands-off on a
# curve at 37 mph it limit-cycles at ~1 Hz, 15 deg p2p: the column holds while the command ramps to
# STEER_MAX, lets go, overshoots to 1.8 m/s2 against 1.0 requested, and the P term (KP ~1.9 there)
# reverses the command before the applied torque has even caught up (#1879, route 0000025e seg 6).
# Hands on the wheel damp it; so does less proportional gain. Scales KP only, KI and the
# feedforward are untouched, other cars are unaffected.
SUSW_KP_SCALE = 0.6

# Fork: SUSW stiction compensator (#1879). The Renegade column sits inside a wide hysteresis band: with a
# persistent lateral-accel error the command climbs for seconds while the steering rate stays at zero,
# then the column breaks free and overshoots. Measured on routes 00000265/266/26d/26e: holds of 1.5 s
# median (p90 2-3 s), break-away at 0.4-0.7 of STEER_MAX, snaps of 2-6 deg. Hands on the wheel fix it
# with a nudge. This does the nudge: once the error has persisted with the column still for
# STICTION_HOLD_TIME, add STICTION_PULSE on top of the command in the direction of the error, withdraw
# it as soon as the column moves (or after STICTION_PULSE_MAX_TIME), then wait STICTION_REFRACTORY.
# The pulse is logged in torqueState.d (unused by this controller otherwise). SUSW cars only.
STICTION_ERROR_MIN = 0.08       # m/s2 of lat-accel error that counts as wanting to move
STICTION_STUCK_RATE = 3.0       # deg/s; the column counts as still below this
STICTION_MOVING_RATE = 8.0      # deg/s; the pulse is withdrawn above this
STICTION_HOLD_TIME = 0.5        # s still, with error, before a pulse
STICTION_PULSE = 0.3            # of STEER_MAX (115 counts), on top of the command; slew applies it in ~230 ms
STICTION_PULSE_MAX_TIME = 0.4   # s
STICTION_REFRACTORY = 0.5       # s after a pulse before the hold timer restarts

class LatControlTorque(LatControl):
  def __init__(self, CP, CI, dt):
    super().__init__(CP, CI, dt)
    self.torque_params = CP.lateralTuning.torque.as_builder()
    self.torque_from_lateral_accel = CI.torque_from_lateral_accel()
    self.lateral_accel_from_torque = CI.lateral_accel_from_torque()
    kp_scale = SUSW_KP_SCALE if CP.carFingerprint in SUSW_CARS else 1.0
    self.stiction_comp = CP.carFingerprint in SUSW_CARS
    self.stuck_time = 0.0
    self.pulse_time = 0.0
    self.pulse_sign = 0.0
    self.refractory_time = 0.0
    self.pid = PIDController([INTERP_SPEEDS, [k * kp_scale for k in KP_INTERP]], KI, rate=1/self.dt)
    self.v_ego = 0.0
    self.update_limits()
    self.steering_angle_deadzone_deg = self.torque_params.steeringAngleDeadzoneDeg
    self.lat_accel_request_buffer_len = int(LAT_ACCEL_REQUEST_BUFFER_SECONDS / self.dt)
    self.lat_accel_request_buffer = deque([0.] * self.lat_accel_request_buffer_len , maxlen=self.lat_accel_request_buffer_len)
    self.lookahead_frames = int(JERK_LOOKAHEAD_SECONDS / self.dt)
    self.jerk_filter = FirstOrderFilter(0.0, 1 / (2 * np.pi * LP_FILTER_CUTOFF_HZ), self.dt)

  def update_live_torque_params(self, latAccelFactor, latAccelOffset, friction):
    self.torque_params.latAccelFactor = latAccelFactor
    self.torque_params.latAccelOffset = latAccelOffset
    self.torque_params.friction = friction
    self.update_limits()

  def update_limits(self):
    # Fork: the torque maps take the speed; the SUSW map is in curvature, so the lat-accel limits move with v^2 (#1879)
    self.pid.set_limits(self.lateral_accel_from_torque(self.steer_max, self.torque_params, self.v_ego),
                        self.lateral_accel_from_torque(-self.steer_max, self.torque_params, self.v_ego))

  def _stiction_pulse(self, CS, error):
    rate = abs(CS.steeringRateDeg)
    if self.pulse_time > 0.0:
      self.pulse_time += self.dt
      if rate > STICTION_MOVING_RATE or self.pulse_time > STICTION_PULSE_MAX_TIME or CS.steeringPressed:
        self.pulse_time = 0.0
        self.stuck_time = 0.0
        self.refractory_time = STICTION_REFRACTORY
        return 0.0
      return self.pulse_sign * STICTION_PULSE * self.steer_max
    if self.refractory_time > 0.0:
      self.refractory_time -= self.dt
      self.stuck_time = 0.0
      return 0.0
    if abs(error) > STICTION_ERROR_MIN and rate < STICTION_STUCK_RATE and not CS.steeringPressed:
      self.stuck_time += self.dt
    else:
      self.stuck_time = 0.0
    if self.stuck_time >= STICTION_HOLD_TIME:
      self.stuck_time = 0.0
      self.pulse_sign = float(np.sign(error))
      self.pulse_time = self.dt
      return self.pulse_sign * STICTION_PULSE * self.steer_max
    return 0.0

  def update(self, active, CS, VM, params, steer_limited_by_safety, desired_curvature, curvature_limited, lat_delay):
    pid_log = log.ControlsState.LateralTorqueState.new_message()
    pid_log.version = VERSION
    self.v_ego = CS.vEgo
    self.update_limits()
    measured_curvature = -VM.calc_curvature(math.radians(CS.steeringAngleDeg - params.angleOffsetDeg), CS.vEgo, params.roll)
    measurement = measured_curvature * CS.vEgo ** 2
    future_desired_lateral_accel = desired_curvature * CS.vEgo ** 2
    self.lat_accel_request_buffer.append(future_desired_lateral_accel)

    roll_compensation = params.roll * ACCELERATION_DUE_TO_GRAVITY
    curvature_deadzone = abs(VM.calc_curvature(math.radians(self.steering_angle_deadzone_deg), CS.vEgo, 0.0))
    lateral_accel_deadzone = curvature_deadzone * CS.vEgo ** 2

    delay_frames = int(np.clip(lat_delay / self.dt + 1, 1, self.lat_accel_request_buffer_len))
    expected_lateral_accel = self.lat_accel_request_buffer[-delay_frames]
    setpoint = expected_lateral_accel
    error = setpoint - measurement

    lookahead_idx = int(np.clip(-delay_frames + self.lookahead_frames, -self.lat_accel_request_buffer_len+1, -2))
    raw_lateral_jerk = (self.lat_accel_request_buffer[lookahead_idx+1] - self.lat_accel_request_buffer[lookahead_idx-1]) / (2 * self.dt)
    desired_lateral_jerk = self.jerk_filter.update(raw_lateral_jerk)
    gravity_adjusted_future_lateral_accel = future_desired_lateral_accel - roll_compensation
    ff = gravity_adjusted_future_lateral_accel
    # latAccelOffset corrects roll compensation bias from device roll misalignment relative to car roll
    ff -= self.torque_params.latAccelOffset
    ff += get_friction(error + JERK_GAIN * desired_lateral_jerk, lateral_accel_deadzone, FRICTION_THRESHOLD, self.torque_params)

    if not active:
      output_torque = 0.0
      pid_log.active = False
      self.stuck_time = self.pulse_time = self.refractory_time = 0.0
    else:
      # do error correction in lateral acceleration space, convert at end to handle non-linear torque responses correctly
      pid_log.error = float(error)

      freeze_integrator = steer_limited_by_safety or CS.steeringPressed or CS.vEgo < 5
      output_lataccel = self.pid.update(pid_log.error, speed=CS.vEgo, feedforward=ff, freeze_integrator=freeze_integrator)
      output_torque = self.torque_from_lateral_accel(output_lataccel, self.torque_params, CS.vEgo)
      pulse = self._stiction_pulse(CS, error) if self.stiction_comp else 0.0
      output_torque = float(np.clip(output_torque + pulse, -self.steer_max, self.steer_max))

      pid_log.active = True
      pid_log.p = float(self.pid.p)
      pid_log.i = float(self.pid.i)
      pid_log.d = float(pulse)
      pid_log.f = float(self.pid.f)
      pid_log.output = float(-output_torque) # TODO: log lat accel?
      pid_log.actualLateralAccel = float(measurement)
      pid_log.desiredLateralAccel = float(setpoint)
      pid_log.desiredLateralJerk = float(desired_lateral_jerk)
      pid_log.saturated = bool(self._check_saturation(self.steer_max - abs(output_torque) < 1e-3, CS, steer_limited_by_safety, curvature_limited))

    # TODO left is positive in this convention
    return -output_torque, 0.0, pid_log
