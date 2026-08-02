// Deterministic two-client SA-MP compatibility fixture.
// Test server only. Do not load this filterscript on a public server.

#include <open.mp>

#pragma tabsize 4

#define SYNC_PAIR_PILOT_NAME       ("SyncPilot")
#define SYNC_PAIR_OBSERVER_NAME    ("SyncObserver")
#define SYNC_PAIR_SAMPLE_MS        (250)
#define SYNC_PAIR_HEARTBEAT_MS     (1000)
#define SYNC_PAIR_REQUEST_POLL_MS  (250)
#define SYNC_PAIR_EDGE_STREAM_RETRY_LIMIT (40)
#define SYNC_PAIR_AUTOSPAWN_RETRY_LIMIT (12)
#define SYNC_PAIR_REQUEST_FILE     ("sync_pair_request.txt")
#define SYNC_PAIR_RESULT_FILE      ("sync_pair_results.log")

#define SYNC_PAIR_X                (206.0)
#define SYNC_PAIR_Y                (1885.0)
#define SYNC_PAIR_Z                (17.65)
#define SYNC_PAIR_TARGET_DISTANCE  (25.0)
#define SYNC_PAIR_PASSENGER_G_X_OFFSET (2.4)

enum E_SYNC_PAIR_SCENARIO
{
    SYNC_PAIR_NONE,
    SYNC_PAIR_ONFOOT,
    SYNC_PAIR_CAR,
    SYNC_PAIR_RUSTLER,
    SYNC_PAIR_PASSENGER,
    SYNC_PAIR_UNOCCUPIED,
    SYNC_PAIR_TRAILER,
    SYNC_PAIR_JETPACK,
    SYNC_PAIR_PICKUP,
    SYNC_PAIR_DEATH,
    SYNC_PAIR_PASSENGER_G
};

static gSyncPilot = INVALID_PLAYER_ID;
static gSyncObserver = INVALID_PLAYER_ID;
static bool:gSyncSpawned[MAX_PLAYERS];
static E_SYNC_PAIR_SCENARIO:gSyncScenario;
static gSyncVehicle = INVALID_VEHICLE_ID;
static gSyncTargetVehicle = INVALID_VEHICLE_ID;
static gSyncTrailer = INVALID_VEHICLE_ID;
static gSyncPickup = -1;
static WEAPON:gSyncWeapon = WEAPON_FIST;
static gSyncLastSampleTick;
static gSyncLastHeartbeatTick;
static gSyncLastKeys;
static gSyncLastUpDown;
static gSyncLastLeftRight;
static PLAYER_STATE:gSyncLastState = PLAYER_STATE_NONE;
static gSyncUpdateCount;
static gSyncShotCount;
static gSyncUnoccupiedUpdateCount;
static gSyncTrailerUpdateCount;
static gSyncActiveRequestId;
static gSyncRequestTimer;
static bool:gSyncPairReadyAnnounced;
static bool:gSyncPassengerEnterSeen;
static gSyncPassengerEnterVehicle = INVALID_VEHICLE_ID;
static gSyncPassengerEnterIsPassenger = -1;
static bool:gSyncPassengerResultEmitted;

forward SyncPairAutoSpawn(playerid, attempt);
forward SyncPairPollRequest();
forward SyncPairRestorePilotWorld();
forward SyncPairFinalizeEdgeSetup(expectedScenario, vehicleid, trailerid, attempt);
forward SyncPairVerifyEdgeSetup(expectedScenario, vehicleid, trailerid, attempt);
forward SyncPairVerifyPassengerEntry(vehicleid, requestId, attempt);

stock SyncPairScenarioName(E_SYNC_PAIR_SCENARIO:scenario, output[], size)
{
    switch (scenario)
    {
        case SYNC_PAIR_ONFOOT: format(output, size, "onfoot");
        case SYNC_PAIR_CAR: format(output, size, "car");
        case SYNC_PAIR_RUSTLER: format(output, size, "rustler");
        case SYNC_PAIR_PASSENGER: format(output, size, "passenger");
        case SYNC_PAIR_UNOCCUPIED: format(output, size, "unoccupied");
        case SYNC_PAIR_TRAILER: format(output, size, "trailer");
        case SYNC_PAIR_JETPACK: format(output, size, "jetpack");
        case SYNC_PAIR_PICKUP: format(output, size, "pickup");
        case SYNC_PAIR_DEATH: format(output, size, "death");
        case SYNC_PAIR_PASSENGER_G: format(output, size, "passenger_g");
        default: format(output, size, "none");
    }
    return 1;
}

stock SyncPairRoleForName(const name[])
{
    if (!strcmp(name, SYNC_PAIR_PILOT_NAME, true)) return 1;
    if (!strcmp(name, SYNC_PAIR_OBSERVER_NAME, true)) return 2;
    return 0;
}

stock SyncPairRole(playerid)
{
    new name[MAX_PLAYER_NAME + 1];
    if (!IsPlayerConnected(playerid)) return 0;
    GetPlayerName(playerid, name, sizeof(name));
    return SyncPairRoleForName(name);
}

stock SyncPairNextToken(const input[], &index, output[], size)
{
    new length = strlen(input);
    new writeIndex;

    output[0] = EOS;
    while (index < length && input[index] <= ' ')
    {
        index++;
    }
    while (index < length && input[index] > ' ' && writeIndex < size - 1)
    {
        output[writeIndex++] = input[index++];
    }
    output[writeIndex] = EOS;
    return writeIndex;
}

stock SyncPairEmitRequestMarker(
    const marker[],
    requestId,
    const status[],
    const scenario[],
    const detail[]
)
{
    new line[256];
    new File:file;

    format(line, sizeof(line),
        "[sync_pair] marker=%s request=%d status=%s scenario=%s detail=%s",
        marker, requestId, status, scenario, detail);
    printf("%s", line);
    file = fopen(SYNC_PAIR_RESULT_FILE, io_append);
    if (file)
    {
        fwrite(file, line);
        fwrite(file, "\r\n");
        fclose(file);
    }
    return 1;
}

stock bool:SyncPairScenarioKnown(const scenario[])
{
    return !strcmp(scenario, "onfoot", true) ||
        !strcmp(scenario, "pistol", true) ||
        !strcmp(scenario, "m4", true) ||
        !strcmp(scenario, "sniper", true) ||
        !strcmp(scenario, "car", true) ||
        !strcmp(scenario, "rustler", true) ||
        !strcmp(scenario, "passenger", true) ||
        !strcmp(scenario, "passenger_g", true) ||
        !strcmp(scenario, "unoccupied", true) ||
        !strcmp(scenario, "trailer", true) ||
        !strcmp(scenario, "jetpack", true) ||
        !strcmp(scenario, "pickup", true) ||
        !strcmp(scenario, "death", true) ||
        !strcmp(scenario, "streamout", true) ||
        !strcmp(scenario, "stop", true);
}

stock SyncPairDestroyVehicles()
{
    if (gSyncVehicle != INVALID_VEHICLE_ID && IsValidVehicle(gSyncVehicle))
    {
        DestroyVehicle(gSyncVehicle);
    }
    if (gSyncTargetVehicle != INVALID_VEHICLE_ID && IsValidVehicle(gSyncTargetVehicle))
    {
        DestroyVehicle(gSyncTargetVehicle);
    }
    if (gSyncTrailer != INVALID_VEHICLE_ID && IsValidVehicle(gSyncTrailer))
    {
        DestroyVehicle(gSyncTrailer);
    }
    gSyncVehicle = INVALID_VEHICLE_ID;
    gSyncTargetVehicle = INVALID_VEHICLE_ID;
    gSyncTrailer = INVALID_VEHICLE_ID;
    return 1;
}

stock SyncPairDestroyPickup()
{
    if (gSyncPickup != -1)
    {
        DestroyPickup(gSyncPickup);
        gSyncPickup = -1;
    }
    return 1;
}

/// Requires both roles to be mutually streamed, not merely spawned.
/// PROBE_TRACE:
/// Run 20260727-194645-sync-edge-all-897587 observed the original pilot's
/// reverse stream-in eleven seconds after the replacement observer spawned.
/// Starting a vehicle scenario at spawn readiness raced that boundary.
/// Reference: https://open.mp/docs/scripting/functions/IsPlayerStreamedIn
stock bool:SyncPairReady()
{
    return gSyncPilot != INVALID_PLAYER_ID &&
        gSyncObserver != INVALID_PLAYER_ID &&
        IsPlayerConnected(gSyncPilot) &&
        IsPlayerConnected(gSyncObserver) &&
        gSyncSpawned[gSyncPilot] &&
        gSyncSpawned[gSyncObserver] &&
        IsPlayerStreamedIn(gSyncPilot, gSyncObserver) &&
        IsPlayerStreamedIn(gSyncObserver, gSyncPilot);
}

stock SyncPairAnnounceReady()
{
    if (!SyncPairReady() || gSyncPairReadyAnnounced)
    {
        return 0;
    }
    gSyncPairReadyAnnounced = true;
    printf("[sync_pair] marker=PAIR_READY pilot=%d observer=%d",
        gSyncPilot, gSyncObserver);
    SendClientMessage(gSyncPilot, 0x66CCFFFF,
        "[sync_pair] Ready: /syncpair pistol | m4 | sniper | car | rustler | passenger | passenger_g | unoccupied | trailer | jetpack | pickup | death | stop");
    return 1;
}

stock bool:SyncPairPilotReady()
{
    return gSyncPilot != INVALID_PLAYER_ID &&
        IsPlayerConnected(gSyncPilot) &&
        gSyncSpawned[gSyncPilot];
}

stock bool:SyncPairScenarioNeedsObserver(const scenario[])
{
    return strcmp(scenario, "jetpack", true) != 0 &&
        strcmp(scenario, "pickup", true) != 0 &&
        strcmp(scenario, "death", true) != 0 &&
        strcmp(scenario, "stop", true) != 0;
}

stock SyncPairResetSampling()
{
    gSyncLastSampleTick = 0;
    gSyncLastHeartbeatTick = 0;
    gSyncLastKeys = 0x7FFFFFFF;
    gSyncLastUpDown = 0x7FFFFFFF;
    gSyncLastLeftRight = 0x7FFFFFFF;
    gSyncLastState = PLAYER_STATE_NONE;
    gSyncUpdateCount = 0;
    gSyncShotCount = 0;
    gSyncUnoccupiedUpdateCount = 0;
    gSyncTrailerUpdateCount = 0;
    gSyncPassengerEnterSeen = false;
    gSyncPassengerEnterVehicle = INVALID_VEHICLE_ID;
    gSyncPassengerEnterIsPassenger = -1;
    gSyncPassengerResultEmitted = false;
    return 1;
}

stock SyncPairPreparePlayers()
{
    for (new index = 0; index < 2; index++)
    {
        new playerid = index == 0 ? gSyncPilot : gSyncObserver;
        if (playerid == INVALID_PLAYER_ID || !IsPlayerConnected(playerid) ||
            !gSyncSpawned[playerid])
        {
            continue;
        }
        SetPlayerInterior(playerid, 0);
        SetPlayerVirtualWorld(playerid, 0);
        SetPlayerHealth(playerid, 100.0);
        SetPlayerArmour(playerid, 0.0);
        SetPlayerTime(playerid, 12, 0);
        SetPlayerWeather(playerid, 10);
        SetPlayerSpecialAction(playerid, SPECIAL_ACTION_NONE);
        ResetPlayerWeapons(playerid);
        SetPlayerPos(playerid, SYNC_PAIR_X, SYNC_PAIR_Y - (index * 6.0), SYNC_PAIR_Z);
    }
    return 1;
}

stock SyncPairSetObserverCamera(Float:targetZ)
{
    SetPlayerPos(gSyncObserver, SYNC_PAIR_X + 18.0, SYNC_PAIR_Y - 8.0, SYNC_PAIR_Z);
    SetPlayerCameraPos(gSyncObserver, SYNC_PAIR_X + 28.0, SYNC_PAIR_Y - 16.0, SYNC_PAIR_Z + 12.0);
    SetPlayerCameraLookAt(gSyncObserver, SYNC_PAIR_X, SYNC_PAIR_Y, targetZ, CAMERA_CUT);
    TogglePlayerControllable(gSyncObserver, false);
    return 1;
}

stock SyncPairSetOnFootObserverCamera()
{
    new Float:midpointY = SYNC_PAIR_Y + (SYNC_PAIR_TARGET_DISTANCE * 0.5);
    SetPlayerPos(gSyncObserver, SYNC_PAIR_X + 42.0, midpointY, SYNC_PAIR_Z);
    SetPlayerCameraPos(gSyncObserver, SYNC_PAIR_X + 34.0, midpointY, SYNC_PAIR_Z + 7.0);
    SetPlayerCameraLookAt(gSyncObserver, SYNC_PAIR_X, midpointY, SYNC_PAIR_Z + 1.0, CAMERA_CUT);
    TogglePlayerControllable(gSyncObserver, false);
    return 1;
}

stock SyncPairBegin(E_SYNC_PAIR_SCENARIO:scenario)
{
    new scenarioName[16];

    if (gSyncPilot == INVALID_PLAYER_ID || !IsPlayerConnected(gSyncPilot) ||
        !gSyncSpawned[gSyncPilot])
    {
        SendClientMessage(gSyncPilot, 0xFF6666FF,
            "[sync_pair] SyncPilot must be connected and spawned.");
        return 0;
    }

    SyncPairDestroyVehicles();
    SyncPairDestroyPickup();
    SyncPairPreparePlayers();
    gSyncScenario = scenario;
    SyncPairResetSampling();
    SyncPairScenarioName(scenario, scenarioName, sizeof(scenarioName));

    switch (scenario)
    {
        case SYNC_PAIR_ONFOOT:
        {
            if (gSyncWeapon == WEAPON_FIST) gSyncWeapon = WEAPON_M4;
            SetPlayerPos(gSyncPilot, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z);
            SetPlayerFacingAngle(gSyncPilot, 0.0);
            SetCameraBehindPlayer(gSyncPilot);
            GivePlayerWeapon(gSyncPilot, gSyncWeapon, 500);
            SetPlayerArmedWeapon(gSyncPilot, gSyncWeapon);
            gSyncTargetVehicle = CreateVehicle(
                411,
                SYNC_PAIR_X,
                SYNC_PAIR_Y + SYNC_PAIR_TARGET_DISTANCE,
                SYNC_PAIR_Z + 0.5,
                90.0,
                1,
                1,
                -1
            );
            if (gSyncTargetVehicle != INVALID_VEHICLE_ID)
            {
                SetVehicleHealth(gSyncTargetVehicle, 5000.0);
            }
            if (SyncPairReady()) SyncPairSetOnFootObserverCamera();
        }
        case SYNC_PAIR_CAR:
        {
            gSyncWeapon = WEAPON_FIST;
            gSyncVehicle = CreateVehicle(411, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z + 0.5,
                180.0, 1, 1, -1);
            PutPlayerInVehicle(gSyncPilot, gSyncVehicle, 0);
            if (SyncPairReady()) SyncPairSetObserverCamera(SYNC_PAIR_Z + 1.5);
        }
        case SYNC_PAIR_RUSTLER:
        {
            gSyncWeapon = WEAPON_FIST;
            gSyncVehicle = CreateVehicle(476, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z + 1.0,
                180.0, 6, 6, -1);
            PutPlayerInVehicle(gSyncPilot, gSyncVehicle, 0);
            if (SyncPairReady()) SyncPairSetObserverCamera(SYNC_PAIR_Z + 2.5);
        }
        case SYNC_PAIR_PASSENGER:
        {
            gSyncWeapon = WEAPON_FIST;
            gSyncVehicle = CreateVehicle(411, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z + 0.5,
                180.0, 1, 1, -1);
            if (SyncPairReady()) SyncPairSetObserverCamera(SYNC_PAIR_Z + 1.5);
            SetTimerEx("SyncPairFinalizeEdgeSetup", 250, false, "iiii",
                _:SYNC_PAIR_PASSENGER, gSyncVehicle, INVALID_VEHICLE_ID, 1);
        }
        case SYNC_PAIR_PASSENGER_G:
        {
            /*
             * STATIC_037:
             * R5's passenger-entry scan rejects vehicles at >= 4.0 units.
             * Model 411 has one unambiguous passenger seat, and the pilot is
             * placed on its right/east side facing west.  No seating native is
             * used: the only transition is the client's local G action.
             */
            gSyncWeapon = WEAPON_FIST;
            SetPlayerPos(
                gSyncPilot,
                SYNC_PAIR_X + SYNC_PAIR_PASSENGER_G_X_OFFSET,
                SYNC_PAIR_Y,
                SYNC_PAIR_Z
            );
            SetPlayerFacingAngle(gSyncPilot, 90.0);
            SetCameraBehindPlayer(gSyncPilot);
            gSyncVehicle = CreateVehicle(
                411,
                SYNC_PAIR_X,
                SYNC_PAIR_Y,
                SYNC_PAIR_Z + 0.5,
                0.0,
                1,
                1,
                -1
            );
            if (gSyncVehicle != INVALID_VEHICLE_ID)
            {
                SetVehicleHealth(gSyncVehicle, 5000.0);
            }
            if (SyncPairReady()) SyncPairSetObserverCamera(SYNC_PAIR_Z + 1.5);
            SetTimerEx("SyncPairFinalizeEdgeSetup", 250, false, "iiii",
                _:SYNC_PAIR_PASSENGER_G, gSyncVehicle, INVALID_VEHICLE_ID, 1);
        }
        case SYNC_PAIR_UNOCCUPIED:
        {
            gSyncWeapon = WEAPON_FIST;
            gSyncVehicle = CreateVehicle(411, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z + 0.5,
                180.0, 1, 1, -1);
            if (SyncPairReady()) SyncPairSetObserverCamera(SYNC_PAIR_Z + 1.5);
            SetTimerEx("SyncPairFinalizeEdgeSetup", 250, false, "iiii",
                _:SYNC_PAIR_UNOCCUPIED, gSyncVehicle, INVALID_VEHICLE_ID, 1);
        }
        case SYNC_PAIR_TRAILER:
        {
            gSyncWeapon = WEAPON_FIST;
            gSyncVehicle = CreateVehicle(515, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z + 0.5,
                180.0, 1, 1, -1);
            gSyncTrailer = CreateVehicle(435, SYNC_PAIR_X, SYNC_PAIR_Y + 8.0,
                SYNC_PAIR_Z + 0.5, 180.0, 1, 1, -1);
            if (SyncPairReady()) SyncPairSetObserverCamera(SYNC_PAIR_Z + 2.0);
            SetTimerEx("SyncPairFinalizeEdgeSetup", 250, false, "iiii",
                _:SYNC_PAIR_TRAILER, gSyncVehicle, gSyncTrailer, 1);
        }
        case SYNC_PAIR_JETPACK:
        {
            gSyncWeapon = WEAPON_FIST;
            SetPlayerPos(gSyncPilot, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z);
            SetPlayerFacingAngle(gSyncPilot, 0.0);
            SetCameraBehindPlayer(gSyncPilot);
            SetPlayerSpecialAction(gSyncPilot, SPECIAL_ACTION_USEJETPACK);
            if (SyncPairReady()) SyncPairSetOnFootObserverCamera();
        }
        case SYNC_PAIR_PICKUP:
        {
            gSyncWeapon = WEAPON_FIST;
            SetPlayerPos(gSyncPilot, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z);
            if (SyncPairReady()) SyncPairSetOnFootObserverCamera();
            gSyncPickup = CreatePickup(
                1240, 1, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z, 0
            );
            printf("[sync_pair] marker=PICKUP_CREATED pickup=%d player=%d",
                gSyncPickup, gSyncPilot);
        }
        case SYNC_PAIR_DEATH:
        {
            gSyncWeapon = WEAPON_FIST;
            SetPlayerPos(gSyncPilot, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z);
            if (SyncPairReady()) SyncPairSetOnFootObserverCamera();
            SetPlayerHealth(gSyncPilot, 0.0);
            printf("[sync_pair] marker=DEATH_TRIGGER player=%d method=health_zero",
                gSyncPilot);
        }
    }

    printf("[sync_pair] marker=SCENARIO_START request=%d scenario=%s pilot=%d observer=%d vehicle=%d target_vehicle=%d trailer=%d weapon=%d",
        gSyncActiveRequestId, scenarioName, gSyncPilot, gSyncObserver, gSyncVehicle,
        gSyncTargetVehicle, gSyncTrailer, _:gSyncWeapon);
    SendClientMessage(gSyncPilot, 0x66FF66FF, "[sync_pair] Scenario ready; host input may start.");
    if (SyncPairReady())
    {
        SendClientMessage(gSyncObserver, 0x66FF66FF, "[sync_pair] Observer camera ready.");
    }
    return 1;
}

stock SyncPairStop(const reason[])
{
    new scenarioName[16];
    SyncPairScenarioName(gSyncScenario, scenarioName, sizeof(scenarioName));
    printf("[sync_pair] marker=SCENARIO_STOP request=%d scenario=%s reason=%s updates=%d shots=%d unoccupied_updates=%d trailer_updates=%d weapon=%d",
        gSyncActiveRequestId, scenarioName, reason, gSyncUpdateCount, gSyncShotCount,
        gSyncUnoccupiedUpdateCount, gSyncTrailerUpdateCount, _:gSyncWeapon);
    SyncPairDestroyVehicles();
    SyncPairDestroyPickup();
    if (gSyncPilot != INVALID_PLAYER_ID && IsPlayerConnected(gSyncPilot))
    {
        SetPlayerSpecialAction(gSyncPilot, SPECIAL_ACTION_NONE);
    }
    if (gSyncObserver != INVALID_PLAYER_ID && IsPlayerConnected(gSyncObserver))
    {
        TogglePlayerControllable(gSyncObserver, true);
        SetCameraBehindPlayer(gSyncObserver);
    }
    gSyncScenario = SYNC_PAIR_NONE;
    gSyncWeapon = WEAPON_FIST;
    return 1;
}

/// Restores a deterministic stream-in after a host-requested stream-out.
/// Reference: https://open.mp/docs/scripting/functions/SetPlayerVirtualWorld
public SyncPairRestorePilotWorld()
{
    if (gSyncPilot != INVALID_PLAYER_ID && IsPlayerConnected(gSyncPilot))
    {
        SetPlayerVirtualWorld(gSyncPilot, 0);
        printf("[sync_pair] marker=STREAM_TRANSITION phase=restore pilot=%d world=0",
            gSyncPilot);
    }
    return 1;
}

stock SyncPairBeginOnFoot(WEAPON:weaponid)
{
    gSyncWeapon = weaponid;
    return SyncPairBegin(SYNC_PAIR_ONFOOT);
}

stock SyncPairBeginNamed(const scenario[])
{
    if (!strcmp(scenario, "onfoot", true)) return SyncPairBeginOnFoot(WEAPON_M4);
    if (!strcmp(scenario, "pistol", true)) return SyncPairBeginOnFoot(WEAPON_COLT45);
    if (!strcmp(scenario, "m4", true)) return SyncPairBeginOnFoot(WEAPON_M4);
    if (!strcmp(scenario, "sniper", true)) return SyncPairBeginOnFoot(WEAPON_SNIPER);
    if (!strcmp(scenario, "car", true)) return SyncPairBegin(SYNC_PAIR_CAR);
    if (!strcmp(scenario, "rustler", true)) return SyncPairBegin(SYNC_PAIR_RUSTLER);
    if (!strcmp(scenario, "passenger", true)) return SyncPairBegin(SYNC_PAIR_PASSENGER);
    if (!strcmp(scenario, "passenger_g", true)) return SyncPairBegin(SYNC_PAIR_PASSENGER_G);
    if (!strcmp(scenario, "unoccupied", true)) return SyncPairBegin(SYNC_PAIR_UNOCCUPIED);
    if (!strcmp(scenario, "trailer", true)) return SyncPairBegin(SYNC_PAIR_TRAILER);
    if (!strcmp(scenario, "jetpack", true)) return SyncPairBegin(SYNC_PAIR_JETPACK);
    if (!strcmp(scenario, "pickup", true)) return SyncPairBegin(SYNC_PAIR_PICKUP);
    if (!strcmp(scenario, "death", true)) return SyncPairBegin(SYNC_PAIR_DEATH);
    return 0;
}

/// Completes edge-state seating/attachment only after the involved vehicles
/// are streamed to both roles.
/// References:
/// https://open.mp/docs/scripting/functions/IsVehicleStreamedIn
/// https://open.mp/docs/scripting/functions/PutPlayerInVehicle
/// https://open.mp/docs/scripting/functions/AttachTrailerToVehicle
/// https://open.mp/docs/scripting/functions/SetVehicleVelocity
public SyncPairFinalizeEdgeSetup(
    expectedScenario,
    vehicleid,
    trailerid,
    attempt
)
{
    new scenarioName[16];
    new detail[160];

    if (_:gSyncScenario != expectedScenario ||
        gSyncVehicle != vehicleid ||
        !SyncPairReady() ||
        !IsValidVehicle(vehicleid))
    {
        SyncPairScenarioName(E_SYNC_PAIR_SCENARIO:expectedScenario,
            scenarioName, sizeof(scenarioName));
        format(detail, sizeof(detail),
            "context_lost vehicle=%d trailer=%d attempt=%d",
            vehicleid, trailerid, attempt);
        SyncPairEmitRequestMarker(
            "EDGE_SETUP",
            gSyncActiveRequestId,
            "FAIL",
            scenarioName,
            detail
        );
        return 0;
    }

    new bool:pilotVehicleStreamed =
        IsVehicleStreamedIn(vehicleid, gSyncPilot);
    new bool:observerVehicleStreamed =
        IsVehicleStreamedIn(vehicleid, gSyncObserver);
    new bool:pilotTrailerStreamed = true;
    new bool:observerTrailerStreamed = true;
    new bool:streamed =
        pilotVehicleStreamed && observerVehicleStreamed;
    if (expectedScenario == _:SYNC_PAIR_TRAILER)
    {
        pilotTrailerStreamed =
            IsVehicleStreamedIn(trailerid, gSyncPilot);
        observerTrailerStreamed =
            IsVehicleStreamedIn(trailerid, gSyncObserver);
        streamed = streamed &&
            gSyncTrailer == trailerid &&
            IsValidVehicle(trailerid) &&
            pilotTrailerStreamed &&
            observerTrailerStreamed;
    }
    if (!streamed)
    {
        if (attempt < SYNC_PAIR_EDGE_STREAM_RETRY_LIMIT)
        {
            SetTimerEx("SyncPairFinalizeEdgeSetup", 250, false, "iiii",
                expectedScenario, vehicleid, trailerid, attempt + 1);
        }
        else
        {
            printf("[sync_pair] marker=EDGE_SETUP status=FAIL scenario=%d vehicle=%d trailer=%d reason=stream_timeout pilot_vehicle=%d observer_vehicle=%d pilot_trailer=%d observer_trailer=%d",
                expectedScenario, vehicleid, trailerid, pilotVehicleStreamed,
                observerVehicleStreamed, pilotTrailerStreamed,
                observerTrailerStreamed);
            SyncPairScenarioName(gSyncScenario, scenarioName, sizeof(scenarioName));
            format(detail, sizeof(detail),
                "stream_timeout vehicle=%d trailer=%d attempts=%d pilot_vehicle=%d observer_vehicle=%d pilot_trailer=%d observer_trailer=%d",
                vehicleid, trailerid, attempt, pilotVehicleStreamed,
                observerVehicleStreamed, pilotTrailerStreamed,
                observerTrailerStreamed);
            SyncPairEmitRequestMarker(
                "EDGE_SETUP",
                gSyncActiveRequestId,
                "FAIL",
                scenarioName,
                detail
            );
        }
        return 0;
    }

    if (expectedScenario == _:SYNC_PAIR_PASSENGER_G)
    {
        new PLAYER_STATE:actualState = GetPlayerState(gSyncPilot);
        new actualVehicle = GetPlayerVehicleID(gSyncPilot);
        new actualSeat = GetPlayerVehicleSeat(gSyncPilot);
        new Float:distance = GetPlayerDistanceFromPoint(
            gSyncPilot,
            SYNC_PAIR_X,
            SYNC_PAIR_Y,
            SYNC_PAIR_Z + 0.5
        );
        new bool:ready =
            actualState == PLAYER_STATE_ONFOOT &&
            actualVehicle == 0 &&
            distance < 4.0;

        if (!ready && attempt < SYNC_PAIR_EDGE_STREAM_RETRY_LIMIT)
        {
            SetTimerEx("SyncPairFinalizeEdgeSetup", 250, false, "iiii",
                expectedScenario, vehicleid, trailerid, attempt + 1);
            return 0;
        }

        SyncPairScenarioName(gSyncScenario, scenarioName, sizeof(scenarioName));
        format(detail, sizeof(detail),
            "vehicle=%d state=%d seat=%d distance=%.3f action=vk_g attempts=%d",
            vehicleid, _:actualState, actualSeat, distance, attempt);
        SyncPairEmitRequestMarker(
            "EDGE_SETUP",
            gSyncActiveRequestId,
            ready ? "PASS" : "FAIL",
            scenarioName,
            detail
        );
        return ready;
    }

    new bool:putResult;
    new bool:velocityResult = true;
    new bool:attachResult = true;
    if (expectedScenario == _:SYNC_PAIR_PASSENGER ||
        expectedScenario == _:SYNC_PAIR_UNOCCUPIED)
    {
        putResult = PutPlayerInVehicle(gSyncPilot, vehicleid, 1);
        if (putResult && expectedScenario == _:SYNC_PAIR_UNOCCUPIED)
        {
            /*
             * STATIC_037 + OPENMP_REF + TODO_VERIFY:
             * A driverless but moving vehicle with the pilot as its first
             * player passenger exercises Packet 209 authority. The official
             * SetVehicleVelocity note requires an occupied vehicle; seating
             * therefore deliberately precedes velocity.
             */
            velocityResult =
                SetVehicleVelocity(vehicleid, 0.0, 0.16, 0.0);
        }
    }
    else if (expectedScenario == _:SYNC_PAIR_TRAILER)
    {
        attachResult = AttachTrailerToVehicle(trailerid, vehicleid);
        putResult = PutPlayerInVehicle(gSyncPilot, vehicleid, 0);
    }

    if (!putResult || !velocityResult || !attachResult)
    {
        printf("[sync_pair] marker=EDGE_SETUP status=FAIL scenario=%d vehicle=%d trailer=%d attempts=%d put=%d velocity=%d attach=%d",
            expectedScenario, vehicleid, trailerid, attempt, putResult,
            velocityResult, attachResult);
        SyncPairScenarioName(gSyncScenario, scenarioName, sizeof(scenarioName));
        format(detail, sizeof(detail),
            "native_failed vehicle=%d put=%d velocity=%d attach=%d",
            vehicleid, putResult, velocityResult, attachResult);
        SyncPairEmitRequestMarker(
            "EDGE_SETUP",
            gSyncActiveRequestId,
            "FAIL",
            scenarioName,
            detail
        );
        return 0;
    }

    SetTimerEx("SyncPairVerifyEdgeSetup", 250, false, "iiii",
        expectedScenario, vehicleid, trailerid, 1);
    return 1;
}

/// Verifies the actual seat/state and trailer relationship after the setup
/// natives have had a server tick to take effect.
/// References:
/// https://open.mp/docs/scripting/functions/GetPlayerVehicleID
/// https://open.mp/docs/scripting/functions/GetPlayerVehicleSeat
/// https://open.mp/docs/scripting/functions/GetPlayerState
/// https://open.mp/docs/scripting/functions/GetVehicleTrailer
public SyncPairVerifyEdgeSetup(
    expectedScenario,
    vehicleid,
    trailerid,
    attempt
)
{
    new scenarioName[16];
    new detail[128];
    new actualVehicle;
    new actualSeat;
    new actualTrailer;
    new PLAYER_STATE:actualState;
    new bool:verified;

    SyncPairScenarioName(E_SYNC_PAIR_SCENARIO:expectedScenario,
        scenarioName, sizeof(scenarioName));
    if (_:gSyncScenario != expectedScenario ||
        gSyncVehicle != vehicleid ||
        !SyncPairReady() ||
        !IsValidVehicle(vehicleid))
    {
        format(detail, sizeof(detail),
            "verify_context_lost vehicle=%d trailer=%d attempt=%d",
            vehicleid, trailerid, attempt);
        SyncPairEmitRequestMarker(
            "EDGE_SETUP",
            gSyncActiveRequestId,
            "FAIL",
            scenarioName,
            detail
        );
        return 0;
    }

    actualVehicle = GetPlayerVehicleID(gSyncPilot);
    actualSeat = GetPlayerVehicleSeat(gSyncPilot);
    actualState = GetPlayerState(gSyncPilot);
    if (expectedScenario == _:SYNC_PAIR_TRAILER)
    {
        actualTrailer = GetVehicleTrailer(vehicleid);
        verified =
            actualVehicle == vehicleid &&
            actualSeat == 0 &&
            actualState == PLAYER_STATE_DRIVER &&
            actualTrailer == trailerid;
    }
    else
    {
        verified =
            actualVehicle == vehicleid &&
            actualSeat == 1 &&
            actualState == PLAYER_STATE_PASSENGER;
    }

    if (!verified && attempt < 12)
    {
        SetTimerEx("SyncPairVerifyEdgeSetup", 250, false, "iiii",
            expectedScenario, vehicleid, trailerid, attempt + 1);
        return 0;
    }

    printf("[sync_pair] marker=EDGE_SETUP status=%s scenario=%d vehicle=%d trailer=%d verify_attempt=%d actual_vehicle=%d actual_seat=%d actual_state=%d actual_trailer=%d",
        verified ? "PASS" : "FAIL", expectedScenario, vehicleid, trailerid,
        attempt, actualVehicle, actualSeat, _:actualState, actualTrailer);
    format(detail, sizeof(detail),
        "vehicle=%d seat=%d state=%d trailer=%d verify_attempt=%d",
        actualVehicle, actualSeat, _:actualState, actualTrailer, attempt);
    SyncPairEmitRequestMarker(
        "EDGE_SETUP",
        gSyncActiveRequestId,
        verified ? "PASS" : "FAIL",
        scenarioName,
        detail
    );
    return verified;
}

/// Verifies that a client-originated passenger request completed physically.
/// The server callback records the request edge, while state/vehicle/seat prove
/// the later PassengerSync state instead of treating entry animation as success.
/// References:
/// https://open.mp/docs/scripting/callbacks/OnPlayerEnterVehicle
/// https://open.mp/docs/scripting/callbacks/OnPlayerStateChange
/// https://open.mp/docs/scripting/functions/GetPlayerVehicleID
/// https://open.mp/docs/scripting/functions/GetPlayerVehicleSeat
public SyncPairVerifyPassengerEntry(vehicleid, requestId, attempt)
{
    if (gSyncScenario != SYNC_PAIR_PASSENGER_G ||
        gSyncVehicle != vehicleid ||
        gSyncActiveRequestId != requestId ||
        gSyncPassengerResultEmitted ||
        !IsPlayerConnected(gSyncPilot))
    {
        return 0;
    }

    new actualVehicle = GetPlayerVehicleID(gSyncPilot);
    new actualSeat = GetPlayerVehicleSeat(gSyncPilot);
    new PLAYER_STATE:actualState = GetPlayerState(gSyncPilot);
    new bool:verified =
        gSyncPassengerEnterSeen &&
        gSyncPassengerEnterVehicle == vehicleid &&
        gSyncPassengerEnterIsPassenger == 1 &&
        actualVehicle == vehicleid &&
        actualSeat == 1 &&
        actualState == PLAYER_STATE_PASSENGER;

    if (!verified && attempt < 20)
    {
        SetTimerEx("SyncPairVerifyPassengerEntry", 250, false, "iii",
            vehicleid, requestId, attempt + 1);
        return 0;
    }

    new detail[160];
    format(detail, sizeof(detail),
        "rpc=26 enter_seen=%d enter_vehicle=%d is_passenger=%d vehicle=%d seat=%d state=%d verify_attempt=%d",
        gSyncPassengerEnterSeen, gSyncPassengerEnterVehicle,
        gSyncPassengerEnterIsPassenger, actualVehicle, actualSeat,
        _:actualState, attempt);
    SyncPairEmitRequestMarker(
        "PASSENGER_ENTRY_RESULT",
        requestId,
        verified ? "PASS" : "FAIL",
        "passenger_g",
        detail
    );
    gSyncPassengerResultEmitted = true;
    return verified;
}

/// Loads the isolated two-client fixture.
/// Reference: https://open.mp/docs/scripting/callbacks/OnFilterScriptInit
public OnFilterScriptInit()
{
    print("[sync_pair] deterministic two-client fixture loaded");
    gSyncRequestTimer = SetTimer("SyncPairPollRequest", SYNC_PAIR_REQUEST_POLL_MS, true);
    /*
     * PROBE_TRACE:
     * Development reloads must not require restarting both comparable clients.
     * Recover the two fixed roles from the server's existing player pool.
     */
    for (new playerid = 0; playerid < MAX_PLAYERS; playerid++)
    {
        if (!IsPlayerConnected(playerid)) continue;
        new role = SyncPairRole(playerid);
        if (!role) continue;
        if (role == 1) gSyncPilot = playerid;
        else gSyncObserver = playerid;
        gSyncSpawned[playerid] = GetPlayerState(playerid) != PLAYER_STATE_NONE;
        printf("[sync_pair] marker=ROLE_RECOVERED role=%s player=%d spawned=%d",
            role == 1 ? "pilot" : "observer", playerid, gSyncSpawned[playerid]);
    }
    SyncPairAnnounceReady();
    return 1;
}

public OnFilterScriptExit()
{
    if (gSyncRequestTimer)
    {
        KillTimer(gSyncRequestTimer);
        gSyncRequestTimer = 0;
    }
    SyncPairStop("filterscript_exit");
    return 1;
}

/// Assigns only the two fixed test nicknames to fixture roles.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerConnect
public OnPlayerConnect(playerid)
{
    new role = SyncPairRole(playerid);
    if (!role) return 1;

    if (role == 1) gSyncPilot = playerid;
    else gSyncObserver = playerid;
    gSyncSpawned[playerid] = false;
    gSyncPairReadyAnnounced = false;
    printf("[sync_pair] marker=ROLE_CONNECTED role=%s player=%d",
        role == 1 ? "pilot" : "observer", playerid);
    SetTimerEx("SyncPairAutoSpawn", 1500, false, "ii", playerid, 1);
    return 1;
}

public OnPlayerDisconnect(playerid, reason)
{
    if (playerid == gSyncPilot || playerid == gSyncObserver)
    {
        printf("[sync_pair] marker=ROLE_DISCONNECTED player=%d reason=%d", playerid, reason);
        SyncPairStop("role_disconnect");
        if (playerid == gSyncPilot) gSyncPilot = INVALID_PLAYER_ID;
        if (playerid == gSyncObserver) gSyncObserver = INVALID_PLAYER_ID;
        gSyncSpawned[playerid] = false;
        gSyncPairReadyAnnounced = false;
    }
    return 1;
}

/// Forces a fixed test-role spawn without affecting other nicknames.
/// PROBE_TRACE:
/// Run 20260727-194906-sync-edge-all-899837 reached InitGame/class selection
/// after the one-shot 1.5-second SpawnPlayer call and never emitted
/// OnPlayerSpawn. Retry until the callback confirms the spawn so client load
/// time is not confused with a compatibility failure.
/// References: https://open.mp/docs/scripting/functions/SetSpawnInfo and /SpawnPlayer
public SyncPairAutoSpawn(playerid, attempt)
{
    if (!IsPlayerConnected(playerid) || !SyncPairRole(playerid)) return 0;
    if (gSyncSpawned[playerid]) return 1;

    SetSpawnInfo(playerid, 0, 0, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z, 180.0,
        WEAPON_M4, 500, WEAPON_DEAGLE, 100, WEAPON_KNIFE, 1);
    new bool:spawnResult = SpawnPlayer(playerid);
    printf("[sync_pair] marker=AUTO_SPAWN player=%d attempt=%d result=%d",
        playerid, attempt, spawnResult);
    if (!gSyncSpawned[playerid] &&
        attempt < SYNC_PAIR_AUTOSPAWN_RETRY_LIMIT)
    {
        SetTimerEx("SyncPairAutoSpawn", 2000, false, "ii",
            playerid, attempt + 1);
    }
    return spawnResult;
}

/// Records role readiness after the forced spawn.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerSpawn
public OnPlayerSpawn(playerid)
{
    new role = SyncPairRole(playerid);
    if (!role) return 1;
    gSyncSpawned[playerid] = true;
    printf("[sync_pair] marker=ROLE_SPAWNED role=%s player=%d",
        role == 1 ? "pilot" : "observer", playerid);
    SyncPairAnnounceReady();
    return 1;
}

/// Starts a named deterministic scenario from the fixed pilot.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerCommandText
public OnPlayerCommandText(playerid, cmdtext[])
{
    if (playerid != gSyncPilot) return 0;
    if (!strcmp(cmdtext, "/syncpair onfoot", true) ||
        !strcmp(cmdtext, "/syncpair pistol", true) ||
        !strcmp(cmdtext, "/syncpair m4", true) ||
        !strcmp(cmdtext, "/syncpair sniper", true) ||
        !strcmp(cmdtext, "/syncpair car", true) ||
        !strcmp(cmdtext, "/syncpair rustler", true) ||
        !strcmp(cmdtext, "/syncpair passenger", true) ||
        !strcmp(cmdtext, "/syncpair passenger_g", true) ||
        !strcmp(cmdtext, "/syncpair unoccupied", true) ||
        !strcmp(cmdtext, "/syncpair trailer", true) ||
        !strcmp(cmdtext, "/syncpair jetpack", true) ||
        !strcmp(cmdtext, "/syncpair pickup", true) ||
        !strcmp(cmdtext, "/syncpair death", true))
    {
        new scenario[16];
        strmid(scenario, cmdtext, 10, strlen(cmdtext), sizeof(scenario));
        gSyncActiveRequestId = 0;
        return SyncPairBeginNamed(scenario);
    }
    if (!strcmp(cmdtext, "/syncpair stop", true))
    {
        gSyncActiveRequestId = 0;
        SyncPairStop("pilot_command");
        return 1;
    }
    return 0;
}

/// Consumes a one-shot host request only after both fixed roles are ready.
/// References: https://open.mp/docs/scripting/functions/fopen,
/// https://open.mp/docs/scripting/functions/fread, and
/// https://open.mp/docs/scripting/functions/fremove
public SyncPairPollRequest()
{
    new File:file = fopen(SYNC_PAIR_REQUEST_FILE, io_read);
    if (!file)
    {
        return 1;
    }

    new line[96];
    new index;
    new requestText[16];
    new scenario[16];
    fread(file, line, sizeof(line));
    fclose(file);
    fremove(SYNC_PAIR_REQUEST_FILE);
    SyncPairNextToken(line, index, requestText, sizeof(requestText));
    SyncPairNextToken(line, index, scenario, sizeof(scenario));

    new requestId = strval(requestText);
    if (requestId <= 0 || !SyncPairScenarioKnown(scenario))
    {
        SyncPairEmitRequestMarker(
            "REQUEST_REJECTED",
            requestId,
            "FAIL",
            strlen(scenario) ? scenario : "none",
            "invalid_request"
        );
        return 1;
    }

    SyncPairEmitRequestMarker("REQUEST_ACCEPTED", requestId, "ACTION", scenario, "host_request");
    if (!SyncPairPilotReady() ||
        (SyncPairScenarioNeedsObserver(scenario) && !SyncPairReady()))
    {
        SyncPairEmitRequestMarker("REQUEST_REJECTED", requestId, "FAIL", scenario, "pair_not_ready");
        return 1;
    }

    gSyncActiveRequestId = requestId;
    if (!strcmp(scenario, "stop", true))
    {
        SyncPairStop("host_request");
        SyncPairEmitRequestMarker("REQUEST_DONE", requestId, "PASS", scenario, "scenario_stopped");
        return 1;
    }
    if (!strcmp(scenario, "streamout", true))
    {
        SetPlayerVirtualWorld(gSyncPilot, 1);
        SetTimer("SyncPairRestorePilotWorld", 1800, false);
        printf("[sync_pair] marker=STREAM_TRANSITION phase=remove pilot=%d world=1",
            gSyncPilot);
        SyncPairEmitRequestMarker(
            "REQUEST_DONE",
            requestId,
            "PASS",
            scenario,
            "streamout_queued"
        );
        return 1;
    }
    if (!SyncPairBeginNamed(scenario))
    {
        SyncPairEmitRequestMarker("REQUEST_REJECTED", requestId, "FAIL", scenario, "scenario_start_failed");
        return 1;
    }
    SyncPairEmitRequestMarker("REQUEST_DONE", requestId, "PASS", scenario, "scenario_started");
    return 1;
}

/// Logs client-originated pilot sync at a bounded rate while returning 1 so
/// open.mp forwards the update to the observer.
/// References: https://open.mp/docs/scripting/callbacks/OnPlayerUpdate and
/// https://open.mp/docs/scripting/functions/GetPlayerKeys,
/// https://open.mp/docs/scripting/functions/GetPlayerFacingAngle,
/// https://open.mp/docs/scripting/functions/GetPlayerSpecialAction and
/// https://open.mp/docs/scripting/functions/GetPlayerRotationQuat,
/// https://open.mp/docs/scripting/functions/GetVehicleZAngle and
/// https://open.mp/docs/scripting/functions/GetVehicleRotationQuat
public OnPlayerUpdate(playerid)
{
    if (playerid != gSyncPilot || gSyncScenario == SYNC_PAIR_NONE) return 1;

    new now = GetTickCount();
    if (now - gSyncLastSampleTick < SYNC_PAIR_SAMPLE_MS) return 1;
    gSyncLastSampleTick = now;

    new KEY:keys;
    new upDown;
    new leftRight;
    new PLAYER_STATE:playerState = GetPlayerState(playerid);
    new Float:x, Float:y, Float:z;
    new Float:vx, Float:vy, Float:vz;
    new Float:cameraX, Float:cameraY, Float:cameraZ;
    new Float:facingAngle;
    new Float:quatW, Float:quatX, Float:quatY, Float:quatZ;
    new Float:vehicleAngle = -1.0;
    new Float:vehicleQuatW, Float:vehicleQuatX, Float:vehicleQuatY, Float:vehicleQuatZ;
    new vehicleId = GetPlayerVehicleID(playerid);
    new Float:zAim = GetPlayerZAim(playerid);
    new cameraMode = GetPlayerCameraMode(playerid);
    new specialAction = GetPlayerSpecialAction(playerid);
    GetPlayerKeys(playerid, keys, upDown, leftRight);
    GetPlayerPos(playerid, x, y, z);
    GetPlayerVelocity(playerid, vx, vy, vz);
    GetPlayerCameraFrontVector(playerid, cameraX, cameraY, cameraZ);
    GetPlayerFacingAngle(playerid, facingAngle);
    GetPlayerRotationQuat(playerid, quatW, quatX, quatY, quatZ);
    if (vehicleId != INVALID_VEHICLE_ID)
    {
        GetVehicleZAngle(vehicleId, vehicleAngle);
        GetVehicleRotationQuat(
            vehicleId,
            vehicleQuatW,
            vehicleQuatX,
            vehicleQuatY,
            vehicleQuatZ
        );
    }
    gSyncUpdateCount++;

    if (_:keys != gSyncLastKeys || upDown != gSyncLastUpDown ||
        leftRight != gSyncLastLeftRight || playerState != gSyncLastState ||
        now - gSyncLastHeartbeatTick >= SYNC_PAIR_HEARTBEAT_MS)
    {
        new scenarioName[16];
        SyncPairScenarioName(gSyncScenario, scenarioName, sizeof(scenarioName));
        printf("[sync_pair] marker=PILOT_SYNC scenario=%s sample=%d state=%d vehicle=%d target_vehicle=%d weapon=%d special=%d keys=0x%x ud=%d lr=%d pos=%.3f,%.3f,%.3f vel=%.4f,%.4f,%.4f facing=%.4f quat=%.5f,%.5f,%.5f,%.5f vehicle_angle=%.4f vehicle_quat=%.5f,%.5f,%.5f,%.5f camera_mode=%d camera_front=%.4f,%.4f,%.4f aim_z=%.4f",
            scenarioName, gSyncUpdateCount, _:playerState, vehicleId,
            gSyncTargetVehicle, _:gSyncWeapon, specialAction, _:keys, upDown, leftRight, x, y, z, vx, vy, vz,
            facingAngle, quatW, quatX, quatY, quatZ,
            vehicleAngle, vehicleQuatW, vehicleQuatX, vehicleQuatY, vehicleQuatZ,
            cameraMode, cameraX, cameraY, cameraZ, zAim);
        gSyncLastHeartbeatTick = now;
        gSyncLastKeys = _:keys;
        gSyncLastUpDown = upDown;
        gSyncLastLeftRight = leftRight;
        gSyncLastState = playerState;
    }
    return 1;
}

/// Records the client-originated death notification and attribution.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerDeath
public OnPlayerDeath(playerid, killerid, WEAPON:reason)
{
    if (playerid == gSyncPilot || playerid == gSyncObserver)
    {
        printf("[sync_pair] marker=PLAYER_DEATH player=%d killer=%d reason=%d scenario=%d",
            playerid, killerid, _:reason, _:gSyncScenario);
    }
    return 1;
}

/// Records RPC 131 pickup completion for the deterministic pickup scenario.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerPickUpPickup
public OnPlayerPickUpPickup(playerid, pickupid)
{
    if (playerid == gSyncPilot && pickupid == gSyncPickup)
    {
        printf("[sync_pair] marker=PICKUP_COLLECTED player=%d pickup=%d scenario=%d",
            playerid, pickupid, _:gSyncScenario);
        SyncPairDestroyPickup();
    }
    return 1;
}

/// Records client-originated Packet 209 while returning 1 so open.mp forwards
/// the update to other streamed players.
/// Reference: https://open.mp/docs/scripting/callbacks/OnUnoccupiedVehicleUpdate
public OnUnoccupiedVehicleUpdate(
    vehicleid,
    playerid,
    passenger_seat,
    Float:new_x,
    Float:new_y,
    Float:new_z,
    Float:vel_x,
    Float:vel_y,
    Float:vel_z
)
{
    if (gSyncScenario == SYNC_PAIR_UNOCCUPIED &&
        playerid == gSyncPilot &&
        vehicleid == gSyncVehicle)
    {
        new detail[96];
        gSyncUnoccupiedUpdateCount++;
        if (gSyncUnoccupiedUpdateCount <= 3 ||
            (gSyncUnoccupiedUpdateCount % 20) == 0)
        {
            printf("[sync_pair] marker=UNOCCUPIED_UPDATE count=%d player=%d vehicle=%d passenger_seat=%d pos=%.3f,%.3f,%.3f vel=%.4f,%.4f,%.4f",
                gSyncUnoccupiedUpdateCount, playerid, vehicleid, passenger_seat,
                new_x, new_y, new_z, vel_x, vel_y, vel_z);
        }
        if (gSyncUnoccupiedUpdateCount == 1)
        {
            format(detail, sizeof(detail),
                "packet=209 player=%d vehicle=%d passenger_seat=%d",
                playerid, vehicleid, passenger_seat);
            SyncPairEmitRequestMarker(
                "UNOCCUPIED_UPDATE",
                gSyncActiveRequestId,
                "PASS",
                "unoccupied",
                detail
            );
        }
    }
    return 1;
}

/// Records client-originated Packet 210 while returning 1 so open.mp forwards
/// the trailer update to other streamed players.
/// Reference: https://open.mp/docs/scripting/callbacks/OnTrailerUpdate
public OnTrailerUpdate(playerid, vehicleid)
{
    if (gSyncScenario == SYNC_PAIR_TRAILER && playerid == gSyncPilot)
    {
        if (vehicleid != gSyncTrailer)
        {
            printf("[sync_pair] marker=TRAILER_UPDATE_MISMATCH player=%d vehicle=%d expected_trailer=%d",
                playerid, vehicleid, gSyncTrailer);
            return 1;
        }
        new detail[80];
        gSyncTrailerUpdateCount++;
        if (gSyncTrailerUpdateCount <= 3 ||
            (gSyncTrailerUpdateCount % 20) == 0)
        {
            printf("[sync_pair] marker=TRAILER_UPDATE count=%d player=%d vehicle=%d expected_trailer=%d",
                gSyncTrailerUpdateCount, playerid, vehicleid, gSyncTrailer);
        }
        if (gSyncTrailerUpdateCount == 1)
        {
            format(detail, sizeof(detail),
                "packet=210 player=%d vehicle=%d",
                playerid, vehicleid);
            SyncPairEmitRequestMarker(
                "TRAILER_UPDATE",
                gSyncActiveRequestId,
                "PASS",
                "trailer",
                detail
            );
        }
    }
    return 1;
}

/// Records the client-originated passenger-entry request before the ped is
/// seated. STATIC_037 maps this R5 request to RPC 26; the callback itself is
/// the server-side semantic receipt, while raw packet capture remains separate.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerEnterVehicle
public OnPlayerEnterVehicle(playerid, vehicleid, ispassenger)
{
    if (gSyncScenario == SYNC_PAIR_PASSENGER_G && playerid == gSyncPilot)
    {
        new bool:firstRequest = !gSyncPassengerEnterSeen;
        new detail[160];
        new PLAYER_STATE:actualState = GetPlayerState(playerid);
        new actualVehicle = GetPlayerVehicleID(playerid);
        new actualSeat = GetPlayerVehicleSeat(playerid);

        gSyncPassengerEnterSeen = true;
        gSyncPassengerEnterVehicle = vehicleid;
        gSyncPassengerEnterIsPassenger = ispassenger;
        format(detail, sizeof(detail),
            "rpc=26 vehicle=%d expected_vehicle=%d is_passenger=%d state_before=%d current_vehicle=%d seat_before=%d",
            vehicleid, gSyncVehicle, ispassenger, _:actualState,
            actualVehicle, actualSeat);
        SyncPairEmitRequestMarker(
            "PASSENGER_ENTER_REQUEST",
            gSyncActiveRequestId,
            "ACTION",
            "passenger_g",
            detail
        );
        if (firstRequest && !gSyncPassengerResultEmitted)
        {
            SetTimerEx("SyncPairVerifyPassengerEntry", 250, false, "iii",
                gSyncVehicle, gSyncActiveRequestId, 1);
        }
    }
    return 1;
}

/// Records driver/on-foot transitions for packet-path comparison.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerStateChange
public OnPlayerStateChange(playerid, PLAYER_STATE:newstate, PLAYER_STATE:oldstate)
{
    if (playerid == gSyncPilot || playerid == gSyncObserver)
    {
        printf("[sync_pair] marker=STATE_CHANGE player=%d old=%d new=%d vehicle=%d",
            playerid, _:oldstate, _:newstate, GetPlayerVehicleID(playerid));
    }
    return 1;
}

/// Confirms bullet sync for ordinary firearms. Vehicle-mounted driver weapons
/// intentionally require observer-side visual evidence instead.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerWeaponShot
public OnPlayerWeaponShot(playerid, WEAPON:weaponid, BULLET_HIT_TYPE:hittype,
    hitid, Float:fX, Float:fY, Float:fZ)
{
    if (playerid == gSyncPilot)
    {
        gSyncShotCount++;
        printf("[sync_pair] marker=WEAPON_SHOT shot=%d weapon=%d expected_weapon=%d hittype=%d hitid=%d target_vehicle=%d pos=%.3f,%.3f,%.3f",
            gSyncShotCount, _:weaponid, _:gSyncWeapon, _:hittype, hitid,
            gSyncTargetVehicle, fX, fY, fZ);
    }
    return 1;
}

/// Records stream-in as the server-side precondition for remote rendering.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerStreamIn
public OnPlayerStreamIn(playerid, forplayerid)
{
    if ((playerid == gSyncPilot && forplayerid == gSyncObserver) ||
        (playerid == gSyncObserver && forplayerid == gSyncPilot))
    {
        printf("[sync_pair] marker=STREAM_IN player=%d for=%d", playerid, forplayerid);
        SyncPairAnnounceReady();
    }
    return 1;
}

/// Records the actual observer-side stream-out boundary.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerStreamOut
public OnPlayerStreamOut(playerid, forplayerid)
{
    if ((playerid == gSyncPilot && forplayerid == gSyncObserver) ||
        (playerid == gSyncObserver && forplayerid == gSyncPilot))
    {
        printf("[sync_pair] marker=STREAM_OUT player=%d for=%d", playerid, forplayerid);
        gSyncPairReadyAnnounced = false;
    }
    return 1;
}
