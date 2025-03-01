# -*- coding: utf-8 -*-
# Eclipse SUMO, Simulation of Urban MObility; see https://eclipse.org/sumo
# Copyright (C) 2008-2022 German Aerospace Center (DLR) and others.
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0/
# This Source Code may also be made available under the following Secondary
# Licenses when the conditions for such availability set forth in the Eclipse
# Public License 2.0 are satisfied: GNU General Public License, version 2
# or later which is available at
# https://www.gnu.org/licenses/old-licenses/gpl-2.0-standalone.html
# SPDX-License-Identifier: EPL-2.0 OR GPL-2.0-or-later

# @file    main.py
# @author  Michael Behrisch
# @author  Lena Kalleske
# @author  Mario Krumnow
# @author  Daniel Krajzewicz
# @author  Jakob Erdmann
# @date    2008-10-09

# pylint: disable=E1101

from __future__ import print_function
from __future__ import absolute_import
import socket
import time
import subprocess
import warnings
import sys
import os

if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sumolib.miscutils import getFreeSocketPort  # noqa

from .domain import DOMAINS  # noqa
# StepListener needs to be imported for backwards compatibility
from .step import StepListener  # noqa
from .connection import Connection  # noqa
from .exceptions import FatalTraCIError, TraCIException  # noqa
from . import _inductionloop, _lanearea, _multientryexit, _trafficlight  # noqa
from . import _variablespeedsign, _meandata  # noqa
from . import _lane, _person, _route, _vehicle, _vehicletype  # noqa
from . import _edge, _gui, _junction, _poi, _polygon, _simulation  # noqa
from . import _calibrator, _routeprobe, _rerouter  # noqa
from . import _busstop, _parkingarea, _chargingstation, _overheadwire  # noqa
from . import constants as tc  # noqa

inductionloop = _inductionloop.InductionLoopDomain()
lanearea = _lanearea.LaneAreaDomain()
multientryexit = _multientryexit.MultiEntryExitDomain()
trafficlight = _trafficlight.TrafficLightDomain()
variablespeedsign = _variablespeedsign.VariableSpeedSignDomain()
meandata = _meandata.MeanDataDomain()
lane = _lane.LaneDomain()
person = _person.PersonDomain()
route = _route.RouteDomain()
vehicle = _vehicle.VehicleDomain()
vehicletype = _vehicletype.VehicleTypeDomain()
edge = _edge.EdgeDomain()
gui = _gui.GuiDomain()
junction = _junction.JunctionDomain()
poi = _poi.PoiDomain()
polygon = _polygon.PolygonDomain()
simulation = _simulation.SimulationDomain()
calibrator = _calibrator.CalibratorDomain()
busstop = _busstop.BusStopDomain()
parkingarea = _parkingarea.ParkingAreaDomain()
chargingstation = _chargingstation.ChargingStationDomain()
overheadwire = _overheadwire.OverheadWireDomain()
routeprobe = _routeprobe.RouteProbeDomain()
rerouter = _rerouter.RerouterDomain()

_connections = {}
# cannot use immutable type as global variable
_currentLabel = [""]
_connectHook = None


def setConnectHook(hookFunc):
    global _connectHook
    _connectHook = hookFunc


def connect(port=8813, numRetries=tc.DEFAULT_NUM_RETRIES, host="localhost", proc=None, waitBetweenRetries=1,
            traceFile=None, traceGetters=True):
    """
    Establish a connection to a TraCI-Server and return the
    connection object. The connection is not saved in the pool and not
    accessible via traci.switch. It should be safe to use different
    connections established by this method in different threads.
    """
    for retry in range(1, numRetries + 2):
        try:
            conn = Connection(host, port, proc, traceFile, traceGetters)
            if _connectHook is not None:
                _connectHook(conn)
            return conn
        except socket.error as e:
            if proc is not None and proc.poll() is not None:
                raise TraCIException("TraCI server already finished")
            if retry > 1:
                print("Could not connect to TraCI server at %s:%s" % (host, port), e)
            if retry < numRetries + 1:
                print(" Retrying in %s seconds" % waitBetweenRetries)
                time.sleep(waitBetweenRetries)
    raise FatalTraCIError("Could not connect in %s tries" % (numRetries + 1))


def init(port=8813, numRetries=tc.DEFAULT_NUM_RETRIES, host="localhost", label="default", proc=None, doSwitch=True,
         traceFile=None, traceGetters=True):
    """
    Establish a connection to a TraCI-Server and store it under the given
    label. This method is not thread-safe. It accesses the connection
    pool concurrently.
    """
    _connections[label] = connect(port, numRetries, host, proc, 1, traceFile, traceGetters)
    if doSwitch:
        switch(label)
    return _connections[label].getVersion()


def start(cmd, port=None, numRetries=tc.DEFAULT_NUM_RETRIES, label="default", verbose=False,
          traceFile=None, traceGetters=True, stdout=None, doSwitch=True):
    """
    Start a sumo server using cmd, establish a connection to it and
    store it under the given label. This method is not thread-safe.

    - cmd (list): uses the Popen syntax. i.e. ['sumo', '-c', 'run.sumocfg']. The remote
      port option will be added automatically
    - numRetries (int): retries on failing to connect to sumo (more retries are needed
      if a big .net.xml file must be loaded)
    - label (string) : distinguish multiple traci connections used in the same script
    - verbose (bool): print complete cmd
    - traceFile (string): write all traci commands to FILE for debugging
    - traceGetters (bool): whether to include get-commands in traceFile
    - stdout (iostream): where to pipe sumo process stdout
    """
    if label in _connections:
        raise TraCIException("Connection '%s' is already active." % label)
    while numRetries >= 0 and label not in _connections:
        sumoPort = getFreeSocketPort() if port is None else port
        cmd2 = cmd + ["--remote-port", str(sumoPort)]
        if verbose:
            print("Calling " + ' '.join(cmd2))
        sumoProcess = subprocess.Popen(cmd2, stdout=stdout)
        try:
            result = init(sumoPort, numRetries, "localhost", label, sumoProcess, doSwitch, traceFile, traceGetters)
            if traceFile is not None:
                _connections[label].write("start", "%s, port=%s, label=%s" % (repr(cmd), repr(port), repr(label)))
            return result
        except TraCIException as e:
            if port is not None:
                break
            warnings.warn(("Could not connect to TraCI server using port %s (%s)." +
                           " Retrying with different port.") % (sumoPort, e))
            numRetries -= 1
    raise FatalTraCIError("Could not connect.")


def isLibsumo():
    return False


def isLibtraci():
    return False


def hasGUI():
    """
    Return whether a GUI and the corresponding GUI commands are available for the current connection.
    """
    if "" not in _connections:
        raise FatalTraCIError("Not connected.")
    return _connections[""].hasGUI()


def load(args):
    """load([optionOrParam, ...])
    Let sumo load a simulation using the given command line like options
    Example:
      load(['-c', 'run.sumocfg'])
      load(['-n', 'net.net.xml', '-r', 'routes.rou.xml'])
    """
    if "" not in _connections:
        raise FatalTraCIError("Not connected.")
    return _connections[""].load(args)


def isLoaded():
    return "" in _connections


def simulationStep(step=0):
    """simulationStep(float) -> list
    Make a simulation step and simulate up to the given second in sim time.
    If the given value is 0 or absent, exactly one step is performed.
    Values smaller than or equal to the current sim time result in no action.
    It returns the subscription results for the current step in a list.
    """
    if "" not in _connections:
        raise FatalTraCIError("Not connected.")
    return _connections[""].simulationStep(step)


def addStepListener(listener):
    """addStepListener(traci.StepListener) -> int

    Append the step listener (its step function is called at the end of every call to traci.simulationStep())
    to the current connection.
    Returns the ID assigned to the listener if it was added successfully, None otherwise.
    """
    if "" not in _connections:
        raise FatalTraCIError("Not connected.")
    return _connections[""].addStepListener(listener)


def removeStepListener(listenerID):
    """removeStepListener(traci.StepListener) -> bool

    Remove the step listener from the current connection's step listener container.
    Returns True if the listener was removed successfully, False if it wasn't registered.
    """
    if "" not in _connections:
        raise FatalTraCIError("Not connected.")
    return _connections[""].removeStepListener(listenerID)


def getVersion():
    """getVersion() -> tuple

    Returns a tuple containing the TraCI API version number (integer)
    and a string identifying the SUMO version running on the TraCI server in human-readable form.
    """
    if "" not in _connections:
        raise FatalTraCIError("Not connected.")
    return _connections[""].getVersion()


def setOrder(order):
    """
    Tells TraCI to give the current client the given position in the
    execution order. It is mandatory to send this as the first command after
    connecting to the TraCI server when using multiple clients. Each client
    must be assigned a unique integer but there are not further restrictions
    on numbering.
    """
    if "" not in _connections:
        raise FatalTraCIError("Not connected.")
    return _connections[""].setOrder(order)


def close(wait=True):
    """
    Tells TraCI to close the connection.
    """
    if "" not in _connections:
        raise FatalTraCIError("Not connected.")
    _connections[""].close(wait)
    _connections[""].simulation._setConnection(None)
    del _connections[_currentLabel[0]]
    del _connections[""]


def switch(label):
    con = getConnection(label)
    _connections[""] = con
    _currentLabel[0] = label
    for domain in DOMAINS:
        domain._setConnection(con)


def getLabel():
    return _currentLabel[0]


def getConnection(label="default"):
    if label not in _connections:
        raise TraCIException("Connection '%s' is not known." % label)
    return _connections[label]


def setLegacyGetLeader(enabled):
    _vehicle._legacyGetLeader = enabled
