import pytest
from openpilot.common.parameterized import parameterized

from openpilot.cereal import log
from opendbc.car.structs import car
from opendbc.car.car_helpers import interfaces
from opendbc.car.honda.values import CAR as HONDA
from opendbc.car.toyota.values import CAR as TOYOTA
from opendbc.car.nissan.values import CAR as NISSAN
from opendbc.car.gm.values import CAR as GM
from opendbc.car.chrysler.values import CAR as CHRYSLER
from opendbc.car.vehicle_model import VehicleModel
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib.latcontrol_pid import LatControlPID
from openpilot.selfdrive.controls.lib.drive_helpers import output_follows_command
from openpilot.selfdrive.controls.lib.latcontrol_torque import (LatControlTorque, SUSW_KP_SCALE, SUSW_KI_UNWIND_SCALE, STICTION_TRIGGER_TAU,
                                                                 STICTION_PULSE_STEP, STICTION_PULSE_MAX, STICTION_ERROR_MIN_CURV, STICTION_HOLD_TIME,
                                                                 STICTION_PULSE, STICTION_PULSE_MAX_TIME, STICTION_PULSE_MIN, STICTION_PULSE_SPEED,
                                                                 STICTION_REFRACTORY)
from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle


class TestLatControl:

  @parameterized.expand([(HONDA.HONDA_CIVIC, LatControlPID), (TOYOTA.TOYOTA_RAV4, LatControlTorque),
                         (NISSAN.NISSAN_LEAF, LatControlAngle), (GM.CHEVROLET_BOLT_EUV, LatControlTorque),
                         (CHRYSLER.JEEP_RENEGADE, LatControlTorque)])
  def test_saturation(self, car_name, controller):
    CarInterface = interfaces[car_name]
    CP = CarInterface.get_non_essential_params(car_name)
    CI = CarInterface(CP)
    VM = VehicleModel(CP)

    controller = controller(CP.as_reader(), CI, DT_CTRL)

    CS = car.CarState.new_message()
    CS.vEgo = 30
    CS.steeringPressed = False

    params = log.LiveParametersData.new_message()

    # Saturate for curvature limited and controller limited
    for _ in range(1000):
      _, _, lac_log = controller.update(True, CS, VM, params, False, 0, True, 0.2)
    assert lac_log.saturated

    for _ in range(1000):
      _, _, lac_log = controller.update(True, CS, VM, params, False, 0, False, 0.2)
    assert not lac_log.saturated

    for _ in range(1000):
      _, _, lac_log = controller.update(True, CS, VM, params, False, 1, False, 0.2)
    assert lac_log.saturated

  def test_susw_kp_scale(self):
    # Fork (#1879): SUSW cars run the torque controller with KP scaled down, KI untouched; others see upstream gains
    def pid_for(car_name):
      CarInterface = interfaces[car_name]
      CP = CarInterface.get_non_essential_params(car_name)
      return LatControlTorque(CP.as_reader(), CarInterface(CP), DT_CTRL).pid

    ref, susw = pid_for(TOYOTA.TOYOTA_RAV4), pid_for(CHRYSLER.JEEP_RENEGADE)
    assert SUSW_KP_SCALE < 1.0
    for speed in (5, 16.5, 30):
      ref.speed = susw.speed = speed
      assert abs(susw.k_p - SUSW_KP_SCALE * ref.k_p) < 1e-9
      assert susw.k_i == ref.k_i

  def test_susw_stiction_pulse(self):
    # Fork (#1879): with a persistent lat-accel error and a still column, SUSW cars get a break-away pulse
    # after STICTION_HOLD_TIME, withdrawn when the column moves or after STICTION_PULSE_MAX_TIME, then a refractory gap
    def make(car_name):
      CarInterface = interfaces[car_name]
      CP = CarInterface.get_non_essential_params(car_name)
      return LatControlTorque(CP.as_reader(), CarInterface(CP), DT_CTRL), VehicleModel(CP)

    def run(ctrl, VM, n, rate=0.0, pressed=False, curvature=0.0005, v_ego=17.):  # 0.5e-3 1/m: above the trigger, command stays off the rail
      out = []
      for _ in range(n):
        CS = car.CarState.new_message()
        CS.vEgo = v_ego
        CS.steeringAngleDeg = 0.
        CS.steeringRateDeg = rate
        CS.steeringPressed = pressed
        params = log.LiveParametersData.new_message()
        torque, _, lac_log = ctrl.update(True, CS, VM, params, False, curvature, False, 0.2)
        out.append((torque, lac_log.d))
      return out

    ctrl, VM = make(CHRYSLER.JEEP_RENEGADE)
    hold = int(STICTION_HOLD_TIME / DT_CTRL)
    delay = int(0.2 / DT_CTRL) + 1  # the setpoint reaches the controller through the lat-delay buffer
    first = run(ctrl, VM, delay + hold - 5)
    assert all(abs(d) < 1e-6 for _, d in first)
    # the trigger reads a low-passed error, so a step takes about STICTION_TRIGGER_TAU to count; stop a few frames into the pulse
    pulsed = []
    for _ in range(15 + 2 * int(STICTION_TRIGGER_TAU / DT_CTRL)):
      pulsed += run(ctrl, VM, 1)
      if abs(pulsed[-1][1]) > 1e-3:
        break
    pulsed += run(ctrl, VM, 3)
    nz = [d for _, d in pulsed if abs(d) > 1e-3]
    assert nz and nz[0] == pytest.approx(STICTION_PULSE * ctrl.steer_max, abs=1e-6)  # error positive -> pulse positive, same sign as the PID torque
    # the pulse adds to the command (controller returns -output_torque, so the returned torque steps by -pulse)
    before = [tq for tq, d in pulsed if abs(d) < 1e-3][-1]
    during = [tq for tq, d in pulsed if abs(d) > 1e-3][0]
    assert during - before == pytest.approx(-STICTION_PULSE * ctrl.steer_max, abs=0.05)
    # the pulse ends when the column moves
    moved = run(ctrl, VM, 1, rate=20.)
    assert abs(moved[0][1]) < 1e-6
    # refractory: no new pulse for STICTION_REFRACTORY even though the column is still again and the error persists
    quiet = run(ctrl, VM, int(STICTION_REFRACTORY / DT_CTRL) + hold - 2)
    assert all(abs(d) < 1e-6 for _, d in quiet)
    again = run(ctrl, VM, 2)
    assert any(abs(d) > 1e-3 for _, d in again)
    # a pulse that never moves the column is capped at STICTION_PULSE_MAX_TIME
    ctrl2, VM2 = make(CHRYSLER.JEEP_RENEGADE)
    seq = run(ctrl2, VM2, delay + hold + int(STICTION_PULSE_MAX_TIME / DT_CTRL) + 5)
    n_pulse = sum(1 for _, d in seq if abs(d) > 1e-3)
    assert 0 < n_pulse <= int(STICTION_PULSE_MAX_TIME / DT_CTRL) + 1
    # hands on the wheel: no pulse
    ctrl3, VM3 = make(CHRYSLER.JEEP_RENEGADE)
    assert all(abs(d) < 1e-6 for _, d in run(ctrl3, VM3, delay + hold * 3, pressed=True))
    # a non-SUSW torque car never pulses
    ctrl4, VM4 = make(TOYOTA.TOYOTA_RAV4)
    assert all(abs(d) < 1e-6 for _, d in run(ctrl4, VM4, delay + hold * 3))
    # the pulse adds to the command and the sum stays within steer_max
    assert all(abs(tq) <= ctrl.steer_max + 1e-9 for tq, _ in first + pulsed + seq)
    # the trigger is in curvature: the same curvature error at 28 m/s still pulses, with the amplitude scaled by (20/28)^2
    ctrl5, VM5 = make(CHRYSLER.JEEP_RENEGADE)
    seq5 = run(ctrl5, VM5, delay + hold + 10 + 2 * int(STICTION_TRIGGER_TAU / DT_CTRL), v_ego=28.)
    nz5 = [d for _, d in seq5 if abs(d) > 1e-3]
    assert nz5 and nz5[0] == pytest.approx(ctrl5.steer_max * max(STICTION_PULSE_MIN, STICTION_PULSE * (STICTION_PULSE_SPEED / 28.) ** 2), abs=1e-6)
    # but a lat-accel error that is below the curvature trigger at 28 m/s (0.0005 * 17^2 / 28^2 ~ 0.18e-3 1/m) never pulses
    ctrl6, VM6 = make(CHRYSLER.JEEP_RENEGADE)
    assert all(abs(d) < 1e-6 for _, d in run(ctrl6, VM6, delay + hold * 3, v_ego=28., curvature=0.0005 * 17. ** 2 / 28. ** 2))
    assert 0.0005 * 17. ** 2 / 28. ** 2 < STICTION_ERROR_MIN_CURV < 0.0005

  def test_susw_integrator_unwind(self):
    # Fork (#1879): on SUSW cars the integral shrinks SUSW_KI_UNWIND_SCALE times faster than it grows; other cars are unchanged
    def make(car_name):
      CarInterface = interfaces[car_name]
      CP = CarInterface.get_non_essential_params(car_name)
      return LatControlTorque(CP.as_reader(), CarInterface(CP), DT_CTRL), VehicleModel(CP)

    def step(ctrl, VM, angle_deg, n, v_ego=30.):
      for _ in range(n):
        CS = car.CarState.new_message()
        CS.vEgo = v_ego
        CS.steeringAngleDeg = angle_deg
        params = log.LiveParametersData.new_message()
        ctrl.update(True, CS, VM, params, False, 0.0, False, 0.2)
      return ctrl.pid.i

    for car_name, scale in ((CHRYSLER.JEEP_RENEGADE, SUSW_KI_UNWIND_SCALE), (TOYOTA.TOYOTA_RAV4, 1.0)):
      ctrl, VM = make(car_name)
      # desired 0, a held steering angle gives a constant measurement, so a constant error of one sign
      i_wound = step(ctrl, VM, 2.0, 100)
      assert abs(i_wound) > 1e-4
      i1 = step(ctrl, VM, 2.0, 1)
      wind_rate = abs(i1 - i_wound)
      # flip the measurement: the error now opposes the integral
      i2 = step(ctrl, VM, -2.0, 1)
      i3 = step(ctrl, VM, -2.0, 1)
      unwind_rate = abs(i3 - i2)
      assert abs(i3) < abs(i2)
      assert unwind_rate / wind_rate == pytest.approx(scale, rel=0.05)

  def test_susw_pulse_escalation(self):
    # Fork (#1879): at highway speed a pulse that does not move the column is followed by a bigger one, up to STICTION_PULSE_MAX;
    # a column move resets the escalation. The trigger reads a filtered error, so an error that flickers around the threshold still fires.
    def make(car_name):
      CarInterface = interfaces[car_name]
      CP = CarInterface.get_non_essential_params(car_name)
      return LatControlTorque(CP.as_reader(), CarInterface(CP), DT_CTRL), VehicleModel(CP)

    def run(ctrl, VM, n, rate=0.0, curvature=0.0005, v_ego=30., alternate=False):
      out = []
      for k in range(n):
        CS = car.CarState.new_message()
        CS.vEgo = v_ego
        CS.steeringRateDeg = rate
        params = log.LiveParametersData.new_message()
        c = curvature * (0.2 if (alternate and k % 2) else 1.8 if alternate else 1.0)
        _, _, lac_log = ctrl.update(True, CS, VM, params, False, c, False, 0.2)
        out.append(lac_log.d)
      return out

    def pulses(seq):
      amps, prev = [], 0.0
      for d in seq:
        if abs(d) > 1e-3 and abs(prev) < 1e-3:
          amps.append(abs(d))
        prev = d
      return amps

    ctrl, VM = make(CHRYSLER.JEEP_RENEGADE)
    period = int((STICTION_HOLD_TIME + STICTION_PULSE_MAX_TIME + STICTION_REFRACTORY) / DT_CTRL) + 10
    amps = pulses(run(ctrl, VM, int(0.2 / DT_CTRL) + 1 + 5 * period))
    assert len(amps) >= 4
    sm = ctrl.steer_max
    assert amps[0] == pytest.approx(STICTION_PULSE_MIN * sm, abs=1e-6)
    assert amps[1] == pytest.approx((STICTION_PULSE_MIN + STICTION_PULSE_STEP) * sm, abs=1e-6)
    assert amps[2] == pytest.approx((STICTION_PULSE_MIN + 2 * STICTION_PULSE_STEP) * sm, abs=1e-6)
    assert max(amps) <= STICTION_PULSE_MAX * sm + 1e-6
    # the column moves: escalation resets to the floor
    run(ctrl, VM, 3, rate=20.)
    amps2 = pulses(run(ctrl, VM, 2 * period))
    assert amps2 and amps2[0] == pytest.approx(STICTION_PULSE_MIN * sm, abs=1e-6)
    # flickering error (0.2x / 1.8x the curvature on alternate frames) still triggers through the filter
    ctrl3, VM3 = make(CHRYSLER.JEEP_RENEGADE)
    assert pulses(run(ctrl3, VM3, int(0.2 / DT_CTRL) + 1 + period, alternate=True))

  def test_output_follows_command(self):
    # Fork (#1879): the output answers a command 1-3 frames old. A command that merely moves (slew-limited ramp of 5 counts
    # per frame = 0.013) is "followed" as long as the output matches one of the last three commands; a clamped output is not.
    hist = [0.100, 0.113, 0.126]  # three frames of a legal ramp
    assert output_follows_command(hist, 0.100, 1e-2)   # output equals the command from 3 frames ago
    assert output_follows_command(hist, 0.113, 1e-2)   # 2 frames ago
    assert output_follows_command(hist, 0.126, 1e-2)   # newest
    assert not output_follows_command(hist, 0.060, 1e-2)  # output pinned well below every recent command: limited
    assert not output_follows_command([0.9, 0.95, 1.0], 0.80, 1e-2)  # driver/safety clamp
    assert output_follows_command([0.0, 0.0, 0.0], 0.0, 1e-2)
