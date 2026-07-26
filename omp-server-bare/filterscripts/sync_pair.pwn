// Deterministic two-client SA-MP compatibility fixture.
// Test server only. Do not load this filterscript on a public server.

#include <open.mp>

#pragma tabsize 4

#define SYNC_PAIR_PILOT_NAME       ("SyncPilot")
#define SYNC_PAIR_OBSERVER_NAME    ("SyncObserver")
#define SYNC_PAIR_SAMPLE_MS        (250)
#define SYNC_PAIR_HEARTBEAT_MS     (1000)
#define SYNC_PAIR_REQUEST_POLL_MS  (250)
#define SYNC_PAIR_REQUEST_FILE     ("sync_pair_request.txt")
#define SYNC_PAIR_RESULT_FILE      ("sync_pair_results.log")

#define SYNC_PAIR_X                (206.0)
#define SYNC_PAIR_Y                (1885.0)
#define SYNC_PAIR_Z                (17.65)
#define SYNC_PAIR_TARGET_DISTANCE  (25.0)

enum E_SYNC_PAIR_SCENARIO
{
    SYNC_PAIR_NONE,
    SYNC_PAIR_ONFOOT,
    SYNC_PAIR_CAR,
    SYNC_PAIR_RUSTLER
};

static gSyncPilot = INVALID_PLAYER_ID;
static gSyncObserver = INVALID_PLAYER_ID;
static bool:gSyncSpawned[MAX_PLAYERS];
static E_SYNC_PAIR_SCENARIO:gSyncScenario;
static gSyncVehicle = INVALID_VEHICLE_ID;
static gSyncTargetVehicle = INVALID_VEHICLE_ID;
static WEAPON:gSyncWeapon = WEAPON_FIST;
static gSyncLastSampleTick;
static gSyncLastHeartbeatTick;
static gSyncLastKeys;
static gSyncLastUpDown;
static gSyncLastLeftRight;
static PLAYER_STATE:gSyncLastState = PLAYER_STATE_NONE;
static gSyncUpdateCount;
static gSyncShotCount;
static gSyncActiveRequestId;
static gSyncRequestTimer;

forward SyncPairAutoSpawn(playerid);
forward SyncPairPollRequest();
forward SyncPairRestorePilotWorld();

stock SyncPairScenarioName(E_SYNC_PAIR_SCENARIO:scenario, output[], size)
{
    switch (scenario)
    {
        case SYNC_PAIR_ONFOOT: format(output, size, "onfoot");
        case SYNC_PAIR_CAR: format(output, size, "car");
        case SYNC_PAIR_RUSTLER: format(output, size, "rustler");
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
    gSyncVehicle = INVALID_VEHICLE_ID;
    gSyncTargetVehicle = INVALID_VEHICLE_ID;
    return 1;
}

stock bool:SyncPairReady()
{
    return gSyncPilot != INVALID_PLAYER_ID &&
        gSyncObserver != INVALID_PLAYER_ID &&
        IsPlayerConnected(gSyncPilot) &&
        IsPlayerConnected(gSyncObserver) &&
        gSyncSpawned[gSyncPilot] &&
        gSyncSpawned[gSyncObserver];
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
    }

    printf("[sync_pair] marker=SCENARIO_START request=%d scenario=%s pilot=%d observer=%d vehicle=%d target_vehicle=%d weapon=%d",
        gSyncActiveRequestId, scenarioName, gSyncPilot, gSyncObserver, gSyncVehicle,
        gSyncTargetVehicle, _:gSyncWeapon);
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
    printf("[sync_pair] marker=SCENARIO_STOP request=%d scenario=%s reason=%s updates=%d shots=%d weapon=%d",
        gSyncActiveRequestId, scenarioName, reason, gSyncUpdateCount, gSyncShotCount,
        _:gSyncWeapon);
    SyncPairDestroyVehicles();
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
    return 0;
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
    if (SyncPairReady())
    {
        printf("[sync_pair] marker=PAIR_READY pilot=%d observer=%d",
            gSyncPilot, gSyncObserver);
    }
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
    printf("[sync_pair] marker=ROLE_CONNECTED role=%s player=%d",
        role == 1 ? "pilot" : "observer", playerid);
    SetTimerEx("SyncPairAutoSpawn", 1500, false, "i", playerid);
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
    }
    return 1;
}

/// Forces a fixed test-role spawn without affecting other nicknames.
/// References: https://open.mp/docs/scripting/functions/SetSpawnInfo and /SpawnPlayer
public SyncPairAutoSpawn(playerid)
{
    if (!IsPlayerConnected(playerid) || !SyncPairRole(playerid)) return 0;
    SetSpawnInfo(playerid, 0, 0, SYNC_PAIR_X, SYNC_PAIR_Y, SYNC_PAIR_Z, 180.0,
        WEAPON_M4, 500, WEAPON_DEAGLE, 100, WEAPON_KNIFE, 1);
    return SpawnPlayer(playerid);
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
    if (SyncPairReady())
    {
        printf("[sync_pair] marker=PAIR_READY pilot=%d observer=%d", gSyncPilot, gSyncObserver);
        SendClientMessage(gSyncPilot, 0x66CCFFFF,
            "[sync_pair] Ready: /syncpair pistol | m4 | sniper | car | rustler | stop");
    }
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
        !strcmp(cmdtext, "/syncpair rustler", true))
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
    if (!SyncPairReady())
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
/// https://open.mp/docs/scripting/functions/GetPlayerFacingAngle and
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
        printf("[sync_pair] marker=PILOT_SYNC scenario=%s sample=%d state=%d vehicle=%d target_vehicle=%d weapon=%d keys=0x%x ud=%d lr=%d pos=%.3f,%.3f,%.3f vel=%.4f,%.4f,%.4f facing=%.4f quat=%.5f,%.5f,%.5f,%.5f vehicle_angle=%.4f vehicle_quat=%.5f,%.5f,%.5f,%.5f camera_mode=%d camera_front=%.4f,%.4f,%.4f aim_z=%.4f",
            scenarioName, gSyncUpdateCount, _:playerState, vehicleId,
            gSyncTargetVehicle, _:gSyncWeapon, _:keys, upDown, leftRight, x, y, z, vx, vy, vz,
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
    }
    return 1;
}
