"""Chrysler SUSW (Jeep Renegade): persist openpilot's LaneSense toggle across key cycles (Redmine #1899).

opendbc owns the toggle (CarState.susw_lanesense_on, flipped by the LaneSense button) but cannot
import Params, so card bridges the two: before the first CarState update it seeds the toggle from
the Param, and after each update it writes the toggle back whenever it has changed. With no Param
yet (the first boot after #1899) the toggle stays None and opendbc seeds it once from the camera's
LANESENSE_DISABLED; that seed is then persisted like any press. Every other car is untouched.
"""
from opendbc.car.chrysler.values import SUSW_CARS

PARAM = "SuswLaneSenseOn"


class SuswLaneSenseParam:
  def __init__(self, params, CI):
    self.params = params
    self.CS = CI.CS if CI.CP.carFingerprint in SUSW_CARS else None
    self.persisted: bool | None = None
    if self.CS is not None:
      self.persisted = params.get(PARAM)   # None when never written
      if self.persisted is not None:
        self.CS.susw_lanesense_on = self.persisted

  def update(self) -> None:
    if self.CS is None:
      return
    toggle = self.CS.susw_lanesense_on
    if toggle is not None and toggle != self.persisted:
      # non-blocking: written off the 100 Hz loop; at most once per button press
      self.params.put_bool(PARAM, toggle)
      self.persisted = toggle
