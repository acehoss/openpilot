"""SUSW LaneSense toggle persistence (Redmine #1899): card seeds opendbc's toggle from a Param and writes it back."""
import pytest

from opendbc.can import CANPacker
from opendbc.car import structs
from opendbc.car.can_definitions import CanData
from opendbc.car.chrysler.interface import CarInterface
from opendbc.car.chrysler.values import CAR
from opendbc.car.toyota.interface import CarInterface as ToyotaInterface
from opendbc.car.toyota.values import CAR as TOYOTA
from openpilot.selfdrive.car.susw_lanesense import PARAM, SuswLaneSenseParam

PRESSED = bytes.fromhex("081da64800000000")    # 0x384 LANESENSE_BUTTON held, route 000000d8 t=69.36
RELEASED = bytes.fromhex("081da60800000000")


class FakeParams:
  """Params.get / put_bool for one BOOL key; get returns None when never written, like the real store."""
  def __init__(self, value=None):
    self.store = {} if value is None else {PARAM: value}
    self.writes = []

  def get(self, key):
    return self.store.get(key)

  def put_bool(self, key, val, block=False):
    self.store[key] = bool(val)
    self.writes.append(bool(val))


class TestSuswLaneSenseParam:
  def setup_method(self):
    CP = CarInterface.get_non_essential_params(CAR.JEEP_RENEGADE)
    self.CI = CarInterface(CP)
    self.nanos = 0
    self.packer = CANPacker("chrysler_susw")

  def _update(self, button=None, camera_disabled=None):
    frames = []
    if button is not None:
      frames.append(CanData(0x384, PRESSED if button else RELEASED, 0))
    if camera_disabled is not None:
      frames.append(CanData(*self.packer.make_can_msg("LKA_HUD_2", 2, {"LANESENSE_DISABLED": int(camera_disabled)})))
    self.nanos += 10_000_000
    return self.CI.update([(self.nanos, frames)])

  @pytest.mark.parametrize("value", [True, False])
  def test_seeds_from_the_param(self, value):
    params = FakeParams(value)
    bridge = SuswLaneSenseParam(params, self.CI)
    assert self.CI.CS.susw_lanesense_on == value
    # the camera saying the opposite does not move it, and nothing is rewritten
    CS = self._update(button=False, camera_disabled=value)
    bridge.update()
    assert CS.laneSenseOn == value
    assert params.writes == []

  def test_first_boot_persists_the_camera_seed(self):
    params = FakeParams()
    bridge = SuswLaneSenseParam(params, self.CI)
    assert self.CI.CS.susw_lanesense_on is None
    self._update(button=False)
    bridge.update()
    assert params.writes == []                     # nothing known yet, nothing written
    self._update(button=False, camera_disabled=False)
    bridge.update()
    assert params.writes == [True]
    assert params.store[PARAM]

  def test_press_is_persisted_once(self):
    params = FakeParams(True)
    bridge = SuswLaneSenseParam(params, self.CI)
    self._update(button=False)
    bridge.update()
    for pressed in [True] * 50 + [False] * 50 + [True, False]:
      self._update(button=pressed)
      bridge.update()
    assert params.writes == [False, True]
    assert params.store[PARAM]

    # and the next key cycle starts from it
    self.setup_method()
    SuswLaneSenseParam(params, self.CI)
    assert self.CI.CS.susw_lanesense_on

  def test_other_cars_untouched(self):
    CP = ToyotaInterface.get_non_essential_params(TOYOTA.TOYOTA_COROLLA_TSS2)
    CI = ToyotaInterface(CP)
    params = FakeParams(False)
    bridge = SuswLaneSenseParam(params, CI)
    bridge.update()
    assert not hasattr(CI.CS, "susw_lanesense_on")
    assert params.writes == []
    assert structs.CarState().laneSenseOn is False
