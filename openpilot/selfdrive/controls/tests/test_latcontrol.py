from openpilot.common.test import OpenpilotTestCase
from openpilot.common.parameterized import parameterized

from openpilot.cereal import log
from opendbc.car.structs import car
from opendbc.car.car_helpers import interfaces
from opendbc.car.honda.values import CAR as HONDA
from opendbc.car.toyota.values import CAR as TOYOTA
from opendbc.car.nissan.values import CAR as NISSAN
from opendbc.car.gm.values import CAR as GM
from opendbc.car.volkswagen.values import CAR as VOLKSWAGEN
from opendbc.car.chrysler.values import CAR as CHRYSLER
from opendbc.car.vehicle_model import VehicleModel
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.controls.lib.latcontrol_pid import LatControlPID
from openpilot.selfdrive.controls.lib.latcontrol_torque import LatControlTorque, SUSW_KP_SCALE
from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle
from openpilot.selfdrive.controls.lib.latcontrol_curvature import LatControlCurvature


class TestLatControl(OpenpilotTestCase):

  @parameterized.expand([(HONDA.HONDA_CIVIC, LatControlPID), (TOYOTA.TOYOTA_RAV4, LatControlTorque),
                         (NISSAN.NISSAN_LEAF, LatControlAngle), (GM.CHEVROLET_BOLT_EUV, LatControlTorque),
                         (VOLKSWAGEN.VOLKSWAGEN_ID4_MK2, LatControlCurvature)])
  def test_saturation(self, car_name, controller):
    CarInterface = interfaces[car_name]
    CP = CarInterface.get_non_essential_params(car_name)
    CI = CarInterface(CP)
    VM = VehicleModel(CP)

    controller = controller(CP.as_reader(), CI, DT_CTRL)

    CS = car.CarState.new_message()
    CS.vEgo = 30
    CS.steeringPressed = False

    params = log.VehicleParameters.new_message()

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
