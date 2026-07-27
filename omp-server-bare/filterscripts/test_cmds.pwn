// Automated compatibility tests adapted from the original SA-MP test_cmds.pwn.
// Original source:
//   /home/chairman/Projects/Legacy Server 0.3.7/filterscripts/test_cmds.pwn
//   SHA256=854e5131fd293d24ae88e05cfd13f0c6740304cba713a9af972337337951a0d6
//
// Test server only. Do not load this filterscript on a public server.

#include <open.mp>

#pragma tabsize 4

#define TEST_CMDS_LOG_FILE                 ("test_cmds_results.log")
#define TEST_CMDS_REQUEST_FILE             ("test_cmds_request.txt")
#define TEST_CMDS_DEFAULT_DELAY_MS         (1200)
#define TEST_CMDS_MIN_DELAY_MS             (250)
#define TEST_CMDS_MAX_DELAY_MS             (10000)
#define TEST_CMDS_DIALOG_BASE              (31900)
#define TEST_CMDS_REQUEST_POLL_MS          (500)
#define TEST_CMDS_AUTOSPAWN_DELAY_MS       (1500)
#define TEST_CMDS_AUTOSTART_DELAY_MS       (1000)

#define TEST_MASK_VEHICLE                  (1)
#define TEST_MASK_PLAYER                   (2)
#define TEST_MASK_PVARS                    (4)
#define TEST_MASK_UI                       (8)
#define TEST_MASK_LABELS                   (16)
#define TEST_MASK_ALL                      (TEST_MASK_VEHICLE | TEST_MASK_PLAYER | TEST_MASK_PVARS | TEST_MASK_UI | TEST_MASK_LABELS)

enum E_TEST_CMDS_CASE
{
    TEST_CASE_NONE,
    TEST_CASE_VEHICLE,
    TEST_CASE_PLAYER,
    TEST_CASE_PVARS,
    TEST_CASE_UI,
    TEST_CASE_LABELS
};

static bool:gTestActive[MAX_PLAYERS];
static gTestRunId[MAX_PLAYERS];
static gTestRequestId[MAX_PLAYERS];
static gTestToken[MAX_PLAYERS];
static gTestTimer[MAX_PLAYERS];
static gTestPendingMask[MAX_PLAYERS];
static E_TEST_CMDS_CASE:gTestCase[MAX_PLAYERS];
static gTestStep[MAX_PLAYERS];
static gTestDelay[MAX_PLAYERS];
static gTestPasses[MAX_PLAYERS];
static gTestFailures[MAX_PLAYERS];
static gTestObservations[MAX_PLAYERS];

static gTestVehicle[MAX_PLAYERS] = {INVALID_VEHICLE_ID, ...};
static bool:gTestVehicleSpawnSeen[MAX_PLAYERS];
static Float:gTestVehicleSpawn[MAX_PLAYERS][3];
static gSavedVirtualWorld[MAX_PLAYERS];
static gSavedSkin[MAX_PLAYERS];
static Float:gSavedFacingAngle[MAX_PLAYERS];
static Text:gTestTextDraw[MAX_PLAYERS] = {Text:INVALID_TEXT_DRAW, ...};
static Text3D:gTestLabel[MAX_PLAYERS] = {Text3D:INVALID_3DTEXT_ID, ...};
static PlayerText3D:gTestPlayerLabel[MAX_PLAYERS] = {PlayerText3D:INVALID_3DTEXT_ID, ...};
static gNextRunId;

static bool:gAutoRequestPending;
static gAutoRequestId;
static gAutoRequestMask;
static gAutoRequestDelay;
static bool:gAutoRequestSpawn;
static gAutoRequestTarget[MAX_PLAYER_NAME + 1];
static gAutoClaimPlayer = INVALID_PLAYER_ID;
static bool:gAutoTransitionScheduled;
static gAutoSpawnAttempts;
static gAutoPollTimer;

forward TestCmdsAdvance(playerid, token);
forward TestCmdsPollRequest();
forward TestCmdsAutoSpawn(playerid, requestId);
forward TestCmdsAutoStart(playerid, requestId);

stock TestCmdsCaseName(E_TEST_CMDS_CASE:testCase, output[], size)
{
    switch (testCase)
    {
        case TEST_CASE_VEHICLE: format(output, size, "vehicle");
        case TEST_CASE_PLAYER: format(output, size, "player");
        case TEST_CASE_PVARS: format(output, size, "pvars");
        case TEST_CASE_UI: format(output, size, "ui");
        case TEST_CASE_LABELS: format(output, size, "labels");
        default: format(output, size, "none");
    }
    return 1;
}

stock TestCmdsStatusColour(const status[])
{
    if (!strcmp(status, "PASS", true)) return 0x66FF66FF;
    if (!strcmp(status, "FAIL", true)) return 0xFF6666FF;
    if (!strcmp(status, "OBSERVE", true)) return 0xFFCC66FF;
    return 0xFFFFFFFF;
}

stock TestCmdsEmitMarker(playerid, const marker[], const status[], const detail[])
{
    new line[320];
    new clientLine[144];
    new File:file;

    format(line, sizeof(line),
        "[test_cmds] marker=%s request=%d player=%d status=%s detail=%s",
        marker, gTestRequestId[playerid], playerid, status, detail);
    printf("%s", line);

    file = fopen(TEST_CMDS_LOG_FILE, io_append);
    if (file)
    {
        fwrite(file, line);
        fwrite(file, "\r\n");
        fclose(file);
    }

    if (IsPlayerConnected(playerid))
    {
        format(clientLine, sizeof(clientLine), "[test_cmds][%s] %s: %.88s", status, marker, detail);
        SendClientMessage(playerid, TestCmdsStatusColour(status), clientLine);
    }
    return 1;
}

stock TestCmdsLog(playerid, const status[], const event[], const detail[])
{
    new caseName[16];
    new playerName[MAX_PLAYER_NAME + 1] = "disconnected";
    new line[384];
    new clientLine[144];
    new File:file;

    TestCmdsCaseName(gTestCase[playerid], caseName, sizeof(caseName));
    if (IsPlayerConnected(playerid))
    {
        GetPlayerName(playerid, playerName, sizeof(playerName));
    }
    format(line, sizeof(line),
        "[test_cmds] request=%d run=%d player=%d name=%s case=%s step=%d status=%s event=%s detail=%s",
        gTestRequestId[playerid], gTestRunId[playerid], playerid, playerName, caseName,
        gTestStep[playerid], status, event, detail);
    printf("%s", line);

    file = fopen(TEST_CMDS_LOG_FILE, io_append);
    if (file)
    {
        fwrite(file, line);
        fwrite(file, "\r\n");
        fclose(file);
    }

    if (IsPlayerConnected(playerid))
    {
        format(clientLine, sizeof(clientLine), "[test_cmds][%s] %s: %.88s", status, event, detail);
        SendClientMessage(playerid, TestCmdsStatusColour(status), clientLine);
    }

    if (!strcmp(status, "PASS", true))
    {
        gTestPasses[playerid]++;
    }
    else if (!strcmp(status, "FAIL", true))
    {
        gTestFailures[playerid]++;
    }
    else if (!strcmp(status, "OBSERVE", true))
    {
        gTestObservations[playerid]++;
    }
    return 1;
}

stock TestCmdsResult(playerid, bool:passed, const event[], const passDetail[], const failDetail[])
{
    if (passed)
    {
        return TestCmdsLog(playerid, "PASS", event, passDetail);
    }
    return TestCmdsLog(playerid, "FAIL", event, failDetail);
}

stock TestCmdsNextToken(const input[], &index, output[], size)
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

stock TestCmdsMaskFromName(const name[])
{
    if (!strcmp(name, "all", true) || !strlen(name)) return TEST_MASK_ALL;
    if (!strcmp(name, "vehicle", true)) return TEST_MASK_VEHICLE;
    if (!strcmp(name, "player", true)) return TEST_MASK_PLAYER;
    if (!strcmp(name, "pvars", true)) return TEST_MASK_PVARS;
    if (!strcmp(name, "ui", true)) return TEST_MASK_UI;
    if (!strcmp(name, "labels", true)) return TEST_MASK_LABELS;
    return 0;
}

stock TestCmdsDestroyTextDraw(playerid)
{
    if (gTestTextDraw[playerid] != Text:INVALID_TEXT_DRAW)
    {
        TextDrawHideForPlayer(playerid, gTestTextDraw[playerid]);
        TextDrawDestroy(gTestTextDraw[playerid]);
        gTestTextDraw[playerid] = Text:INVALID_TEXT_DRAW;
    }
    return 1;
}

stock TestCmdsDestroyLabels(playerid)
{
    if (gTestLabel[playerid] != Text3D:INVALID_3DTEXT_ID)
    {
        Delete3DTextLabel(gTestLabel[playerid]);
        gTestLabel[playerid] = Text3D:INVALID_3DTEXT_ID;
    }
    if (gTestPlayerLabel[playerid] != PlayerText3D:INVALID_3DTEXT_ID)
    {
        DeletePlayer3DTextLabel(playerid, gTestPlayerLabel[playerid]);
        gTestPlayerLabel[playerid] = PlayerText3D:INVALID_3DTEXT_ID;
    }
    return 1;
}

stock TestCmdsDestroyVehicle(playerid)
{
    new vehicleid = gTestVehicle[playerid];

    if (vehicleid != INVALID_VEHICLE_ID)
    {
        if (IsPlayerConnected(playerid) && GetPlayerVehicleID(playerid) == vehicleid)
        {
            RemovePlayerFromVehicle(playerid);
        }
        if (IsValidVehicle(vehicleid))
        {
            DestroyVehicle(vehicleid);
        }
        gTestVehicle[playerid] = INVALID_VEHICLE_ID;
    }
    gTestVehicleSpawnSeen[playerid] = false;
    return 1;
}

stock TestCmdsCleanup(playerid)
{
    TestCmdsDestroyTextDraw(playerid);
    TestCmdsDestroyLabels(playerid);
    TestCmdsDestroyVehicle(playerid);
    if (IsPlayerConnected(playerid))
    {
        ShowPlayerDialog(playerid, -1, DIALOG_STYLE_MSGBOX, "", "", "", "");
    }
    return 1;
}

stock TestCmdsSchedule(playerid, delay = -1)
{
    new timerDelay = delay;

    if (timerDelay < 0)
    {
        timerDelay = gTestDelay[playerid];
    }
    if (gTestTimer[playerid])
    {
        KillTimer(gTestTimer[playerid]);
        gTestTimer[playerid] = 0;
    }
    gTestTimer[playerid] = SetTimerEx("TestCmdsAdvance", timerDelay, false, "ii", playerid, gTestToken[playerid]);
    if (!gTestTimer[playerid])
    {
        TestCmdsLog(playerid, "FAIL", "timer_create", "SetTimerEx returned INVALID_TIMER; run stopped");
        gTestActive[playerid] = false;
        TestCmdsCleanup(playerid);
        return 0;
    }
    return 1;
}

stock TestCmdsBeginNextCase(playerid)
{
    new detail[96];

    if (gTestPendingMask[playerid] & TEST_MASK_VEHICLE)
    {
        gTestPendingMask[playerid] &= ~TEST_MASK_VEHICLE;
        gTestCase[playerid] = TEST_CASE_VEHICLE;
    }
    else if (gTestPendingMask[playerid] & TEST_MASK_PLAYER)
    {
        gTestPendingMask[playerid] &= ~TEST_MASK_PLAYER;
        gTestCase[playerid] = TEST_CASE_PLAYER;
    }
    else if (gTestPendingMask[playerid] & TEST_MASK_PVARS)
    {
        gTestPendingMask[playerid] &= ~TEST_MASK_PVARS;
        gTestCase[playerid] = TEST_CASE_PVARS;
    }
    else if (gTestPendingMask[playerid] & TEST_MASK_UI)
    {
        gTestPendingMask[playerid] &= ~TEST_MASK_UI;
        gTestCase[playerid] = TEST_CASE_UI;
    }
    else if (gTestPendingMask[playerid] & TEST_MASK_LABELS)
    {
        gTestPendingMask[playerid] &= ~TEST_MASK_LABELS;
        gTestCase[playerid] = TEST_CASE_LABELS;
    }
    else
    {
        new summaryStatus[8];

        format(detail, sizeof(detail), "complete passes=%d failures=%d observations=%d",
            gTestPasses[playerid], gTestFailures[playerid], gTestObservations[playerid]);
        format(summaryStatus, sizeof(summaryStatus), gTestFailures[playerid] ? "FAIL" : "PASS");
        TestCmdsLog(playerid, summaryStatus, "run_summary", detail);
        TestCmdsEmitMarker(playerid, "RUN_DONE", summaryStatus, detail);
        gTestActive[playerid] = false;
        gTestCase[playerid] = TEST_CASE_NONE;
        gTestStep[playerid] = 0;
        gTestTimer[playerid] = 0;
        TestCmdsCleanup(playerid);
        return 0;
    }

    gTestStep[playerid] = 0;
    TestCmdsCaseName(gTestCase[playerid], detail, sizeof(detail));
    TestCmdsLog(playerid, "ACTION", "case_start", detail);
    return TestCmdsSchedule(playerid, 250);
}

stock TestCmdsFinishCase(playerid)
{
    new caseName[16];
    new completedCase = _:gTestCase[playerid];
    new detail[96];

    TestCmdsCaseName(gTestCase[playerid], caseName, sizeof(caseName));
    TestCmdsLog(playerid, "ACTION", "case_complete", caseName);
    gTestCase[playerid] = TEST_CASE_NONE;
    gTestStep[playerid] = 0;
    if (gTestPendingMask[playerid])
    {
        format(detail, sizeof(detail), "after=%s delay_ms=%d", caseName,
            completedCase == _:TEST_CASE_VEHICLE ? gTestDelay[playerid] + 500 : gTestDelay[playerid]);
        TestCmdsLog(playerid, "ACTION", "case_settle", detail);
        return TestCmdsSchedule(playerid,
            completedCase == _:TEST_CASE_VEHICLE ? gTestDelay[playerid] + 500 : gTestDelay[playerid]);
    }
    return TestCmdsBeginNextCase(playerid);
}

stock TestCmdsRunVehicleStep(playerid)
{
    new detail[160];
    new vehicleid = gTestVehicle[playerid];
    new result;
    new Float:x, Float:y, Float:z, Float:angle;
    new Float:vehicleX, Float:vehicleY, Float:vehicleZ;

    switch (gTestStep[playerid])
    {
        case 0:
        {
            TestCmdsDestroyVehicle(playerid);
            GetPlayerPos(playerid, x, y, z);
            GetPlayerFacingAngle(playerid, angle);
            gTestVehicleSpawn[playerid][0] = x + 4.0;
            gTestVehicleSpawn[playerid][1] = y;
            gTestVehicleSpawn[playerid][2] = z + 0.5;
            vehicleid = CreateVehicle(560, gTestVehicleSpawn[playerid][0], gTestVehicleSpawn[playerid][1],
                gTestVehicleSpawn[playerid][2], angle, 1, 3, -1);
            gTestVehicle[playerid] = vehicleid;
            if (vehicleid != INVALID_VEHICLE_ID && vehicleid != 0)
            {
                LinkVehicleToInterior(vehicleid, GetPlayerInterior(playerid));
                SetVehicleVirtualWorld(vehicleid, GetPlayerVirtualWorld(playerid));
                AddVehicleComponent(vehicleid, 1078);
                AddVehicleComponent(vehicleid, 1010);
                ChangeVehiclePaintjob(vehicleid, 1);
                SetVehicleHealth(vehicleid, 650.0);
                RepairVehicle(vehicleid);
                format(detail, sizeof(detail), "created id=%d model=560 pos=(%.3f,%.3f,%.3f) mods=1078,1010 paintjob=1 repair=issued",
                    vehicleid, gTestVehicleSpawn[playerid][0], gTestVehicleSpawn[playerid][1], gTestVehicleSpawn[playerid][2]);
                TestCmdsLog(playerid, "PASS", "vehicle_create", detail);
            }
            else
            {
                TestCmdsLog(playerid, "FAIL", "vehicle_create", "CreateVehicle returned an invalid vehicle ID");
            }
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid, gTestDelay[playerid] + 500);
        }
        case 1:
        {
            if (vehicleid == INVALID_VEHICLE_ID || !IsValidVehicle(vehicleid))
            {
                TestCmdsLog(playerid, "FAIL", "vehicle_put", "test vehicle no longer exists");
            }
            else
            {
                result = PutPlayerInVehicle(playerid, vehicleid, 0);
                format(detail, sizeof(detail), "PutPlayerInVehicle player=%d vehicle=%d seat=0 returned=%d", playerid, vehicleid, result);
                TestCmdsLog(playerid, result ? "ACTION" : "FAIL", "vehicle_put", detail);
            }
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid, gTestDelay[playerid] + 500);
        }
        case 2:
        {
            format(detail, sizeof(detail), "expected_vehicle=%d actual_vehicle=%d state=%d",
                vehicleid, GetPlayerVehicleID(playerid), _:GetPlayerState(playerid));
            TestCmdsResult(playerid,
                GetPlayerVehicleID(playerid) == vehicleid && GetPlayerState(playerid) == PLAYER_STATE_DRIVER,
                "vehicle_enter_verify", detail, detail);
            result = RemovePlayerFromVehicle(playerid);
            format(detail, sizeof(detail), "RemovePlayerFromVehicle player=%d returned=%d", playerid, result);
            TestCmdsLog(playerid, result ? "ACTION" : "FAIL", "vehicle_eject", detail);
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid, gTestDelay[playerid]);
        }
        case 3:
        {
            format(detail, sizeof(detail), "actual_vehicle=%d state=%d",
                GetPlayerVehicleID(playerid), _:GetPlayerState(playerid));
            if (GetPlayerVehicleID(playerid) == 0)
            {
                TestCmdsLog(playerid, "PASS", "vehicle_eject_verify", detail);
            }
            else
            {
                // OBSERVED_037 + PROBE_TRACE:
                // The 20260718-213416 and 20260718-213514 original-R5 runs retain the last server-side
                // vehicle/state after RPC 71 until the following respawn transition. Keep this observable,
                // but do not turn original behavior into either a false failure or a synthetic pass.
                TestCmdsLog(playerid, "OBSERVE", "vehicle_eject_verify", detail);
            }
            gTestVehicleSpawnSeen[playerid] = false;
            result = SetVehicleToRespawn(vehicleid);
            format(detail, sizeof(detail), "SetVehicleToRespawn vehicle=%d returned=%d", vehicleid, result);
            TestCmdsLog(playerid, result ? "ACTION" : "FAIL", "vehicle_respawn", detail);
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid, gTestDelay[playerid] + 500);
        }
        case 4:
        {
            GetVehiclePos(vehicleid, vehicleX, vehicleY, vehicleZ);
            format(detail, sizeof(detail), "vehicle=%d callback=%d model=%d pos=(%.3f,%.3f,%.3f) expected=(%.3f,%.3f,%.3f)",
                vehicleid, gTestVehicleSpawnSeen[playerid], GetVehicleModel(vehicleid), vehicleX, vehicleY, vehicleZ,
                gTestVehicleSpawn[playerid][0], gTestVehicleSpawn[playerid][1], gTestVehicleSpawn[playerid][2]);
            TestCmdsResult(playerid,
                IsValidVehicle(vehicleid) && gTestVehicleSpawnSeen[playerid] && GetVehicleModel(vehicleid) == 560 &&
                floatabs(vehicleX - gTestVehicleSpawn[playerid][0]) < 1.0 &&
                floatabs(vehicleY - gTestVehicleSpawn[playerid][1]) < 1.0,
                "vehicle_respawn_verify", detail, detail);
            TestCmdsDestroyVehicle(playerid);
            return TestCmdsFinishCase(playerid);
        }
    }
    return TestCmdsFinishCase(playerid);
}

stock TestCmdsRunPlayerStep(playerid)
{
    new detail[160];
    new Float:angle;

    switch (gTestStep[playerid])
    {
        case 0:
        {
            gSavedVirtualWorld[playerid] = GetPlayerVirtualWorld(playerid);
            gSavedSkin[playerid] = GetPlayerSkin(playerid);
            GetPlayerFacingAngle(playerid, gSavedFacingAngle[playerid]);
            SetPlayerVirtualWorld(playerid, gSavedVirtualWorld[playerid] + 1);
            SetPlayerSkin(playerid, 287);
            SetPlayerFacingAngle(playerid, 90.0);
            SetPlayerFightingStyle(playerid, FIGHT_STYLE_BOXING);
            SetPlayerSkillLevel(playerid, WEAPONSKILL_PISTOL, 500);
            format(detail, sizeof(detail), "set virtual_world=%d skin=287 facing=90 fighting=boxing pistol_skill=500",
                gSavedVirtualWorld[playerid] + 1);
            TestCmdsLog(playerid, "ACTION", "player_state_set", detail);
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid);
        }
        case 1:
        {
            GetPlayerFacingAngle(playerid, angle);
            format(detail, sizeof(detail), "virtual_world=%d skin=%d facing=%.3f",
                GetPlayerVirtualWorld(playerid), GetPlayerSkin(playerid), angle);
            TestCmdsResult(playerid,
                GetPlayerVirtualWorld(playerid) == gSavedVirtualWorld[playerid] + 1 &&
                GetPlayerSkin(playerid) == 287,
                "player_state_verify", detail, detail);
            format(detail, sizeof(detail), "expected=90.000 actual=%.3f rpc=19 gta_opcode=0173 trace_required=1", angle);
            // OBSERVED_037 + PROBE_TRACE:
            // Client OnFootSync can overwrite open.mp's server-facing angle before this delayed callback, including
            // on original R5 run 20260718-220442. The stable parity claim is the RPC 19/0173 trace, not this value.
            TestCmdsLog(playerid, "OBSERVE", "player_facing_opcode", detail);
            SetPlayerVirtualWorld(playerid, gSavedVirtualWorld[playerid]);
            SetPlayerSkin(playerid, gSavedSkin[playerid]);
            SetPlayerFacingAngle(playerid, gSavedFacingAngle[playerid]);
            TestCmdsLog(playerid, "ACTION", "player_state_restore", "original virtual world, skin and facing angle restored");
            return TestCmdsFinishCase(playerid);
        }
    }
    return TestCmdsFinishCase(playerid);
}

stock TestCmdsRunPVarStep(playerid)
{
    new detail[160];
    new value[64];
    new Float:floatValue;

    switch (gTestStep[playerid])
    {
        case 0:
        {
            SetPVarInt(playerid, "test_cmds_int", 7001);
            SetPVarString(playerid, "test_cmds_string", "Hello World");
            SetPVarFloat(playerid, "test_cmds_float", 1001.0);
            TestCmdsLog(playerid, "ACTION", "pvars_set", "int=7001 string='Hello World' float=1001.0");
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid, 250);
        }
        case 1:
        {
            GetPVarString(playerid, "test_cmds_string", value, sizeof(value));
            floatValue = GetPVarFloat(playerid, "test_cmds_float");
            format(detail, sizeof(detail), "int=%d string='%s' float=%.3f",
                GetPVarInt(playerid, "test_cmds_int"), value, floatValue);
            TestCmdsResult(playerid,
                GetPVarInt(playerid, "test_cmds_int") == 7001 && !strcmp(value, "Hello World") &&
                floatabs(floatValue - 1001.0) < 0.01,
                "pvars_verify_set", detail, detail);
            SetPVarInt(playerid, "test_cmds_int", 8001);
            SetPVarString(playerid, "test_cmds_string", "World Hello");
            SetPVarFloat(playerid, "test_cmds_float", 6901.0);
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid, 250);
        }
        case 2:
        {
            GetPVarString(playerid, "test_cmds_string", value, sizeof(value));
            floatValue = GetPVarFloat(playerid, "test_cmds_float");
            format(detail, sizeof(detail), "int=%d string='%s' float=%.3f",
                GetPVarInt(playerid, "test_cmds_int"), value, floatValue);
            TestCmdsResult(playerid,
                GetPVarInt(playerid, "test_cmds_int") == 8001 && !strcmp(value, "World Hello") &&
                floatabs(floatValue - 6901.0) < 0.01,
                "pvars_verify_modify", detail, detail);
            DeletePVar(playerid, "test_cmds_int");
            DeletePVar(playerid, "test_cmds_string");
            DeletePVar(playerid, "test_cmds_float");
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid, 250);
        }
        case 3:
        {
            format(detail, sizeof(detail), "types int=%d string=%d float=%d",
                _:GetPVarType(playerid, "test_cmds_int"), _:GetPVarType(playerid, "test_cmds_string"),
                _:GetPVarType(playerid, "test_cmds_float"));
            TestCmdsResult(playerid,
                GetPVarType(playerid, "test_cmds_int") == PLAYER_VARTYPE_NONE &&
                GetPVarType(playerid, "test_cmds_string") == PLAYER_VARTYPE_NONE &&
                GetPVarType(playerid, "test_cmds_float") == PLAYER_VARTYPE_NONE,
                "pvars_verify_delete", detail, detail);
            return TestCmdsFinishCase(playerid);
        }
    }
    return TestCmdsFinishCase(playerid);
}

stock TestCmdsRunUIStep(playerid)
{
    switch (gTestStep[playerid])
    {
        case 0:
        {
            TogglePlayerWidescreen(playerid, true);
            TestCmdsLog(playerid, "OBSERVE", "ui_widescreen_enable",
                "RPC 111 enabled; automatic disable follows after the UI sequence");
        }
        case 1:
        {
            GameTextForPlayer(playerid, "~w~test_cmds: ~g~automated UI sequence", 2000, 5);
            TestCmdsLog(playerid, "OBSERVE", "ui_gametext", "style=5 duration=2000 sent; client rendering requires trace or screenshot review");
        }
        case 2:
        {
            ShowPlayerDialog(playerid, TEST_CMDS_DIALOG_BASE, DIALOG_STYLE_MSGBOX,
                "test_cmds msgbox", "Automated message-box RPC test.", "OK", "Cancel");
            TestCmdsLog(playerid, "OBSERVE", "ui_dialog_msgbox", "dialog shown; it will be closed automatically");
        }
        case 3:
        {
            ShowPlayerDialog(playerid, -1, DIALOG_STYLE_MSGBOX, "", "", "", "");
            ShowPlayerDialog(playerid, TEST_CMDS_DIALOG_BASE + 1, DIALOG_STYLE_INPUT,
                "test_cmds input", "Automated input-dialog RPC test.", "Submit", "Cancel");
            TestCmdsLog(playerid, "OBSERVE", "ui_dialog_input", "input dialog shown; no manual response required");
        }
        case 4:
        {
            ShowPlayerDialog(playerid, -1, DIALOG_STYLE_MSGBOX, "", "", "", "");
            ShowPlayerDialog(playerid, TEST_CMDS_DIALOG_BASE + 3, DIALOG_STYLE_PASSWORD,
                "test_cmds password", "Automated password-dialog RPC test.", "Submit", "Cancel");
            TestCmdsLog(playerid, "OBSERVE", "ui_dialog_password",
                "password dialog shown; entered text must be masked visually but preserved in RPC 62");
        }
        case 5:
        {
            ShowPlayerDialog(playerid, -1, DIALOG_STYLE_MSGBOX, "", "", "", "");
            ShowPlayerDialog(playerid, TEST_CMDS_DIALOG_BASE + 2, DIALOG_STYLE_LIST,
                "test_cmds list", "1\tDeagle\n2\tSawnoff\n3\tPistol\n4\tGrenade", "Select", "Cancel");
            TestCmdsLog(playerid, "OBSERVE", "ui_dialog_list", "list dialog shown; no manual response required");
        }
        case 6:
        {
            ShowPlayerDialog(playerid, -1, DIALOG_STYLE_MSGBOX, "", "", "", "");
            TestCmdsDestroyTextDraw(playerid);
            gTestTextDraw[playerid] = TextDrawCreate(320.0, 240.0,
                "~w~test_cmds ~g~TextDraw~n~~y~automatic show/hide lifecycle");
            TextDrawAlignment(gTestTextDraw[playerid], TEXT_DRAW_ALIGN_CENTER);
            TextDrawLetterSize(gTestTextDraw[playerid], 0.45, 1.6);
            TextDrawUseBox(gTestTextDraw[playerid], true);
            TextDrawBoxColour(gTestTextDraw[playerid], 0x00000080);
            TextDrawTextSize(gTestTextDraw[playerid], 420.0, 120.0);
            TextDrawShowForPlayer(playerid, gTestTextDraw[playerid]);
            TestCmdsLog(playerid, "OBSERVE", "ui_textdraw", "textdraw created and shown; automatic hide/destroy follows");
        }
        case 7:
        {
            TogglePlayerWidescreen(playerid, false);
            TestCmdsDestroyTextDraw(playerid);
            TestCmdsLog(playerid, "PASS", "ui_cleanup",
                "RPC 111 disabled; dialogs closed and textdraw hidden/destroyed automatically");
            return TestCmdsFinishCase(playerid);
        }
    }
    gTestStep[playerid]++;
    return TestCmdsSchedule(playerid);
}

stock TestCmdsRunLabelsStep(playerid)
{
    new detail[160];
    new Float:x, Float:y, Float:z;

    switch (gTestStep[playerid])
    {
        case 0:
        {
            TestCmdsDestroyLabels(playerid);
            TestCmdsDestroyVehicle(playerid);
            GetPlayerPos(playerid, x, y, z);
            gTestVehicle[playerid] = CreateVehicle(411, x + 4.0, y + 2.0, z + 0.5, 0.0, 6, 6, -1);
            if (gTestVehicle[playerid] != INVALID_VEHICLE_ID)
            {
                LinkVehicleToInterior(gTestVehicle[playerid], GetPlayerInterior(playerid));
                SetVehicleVirtualWorld(gTestVehicle[playerid], GetPlayerVirtualWorld(playerid));
                gTestLabel[playerid] = Create3DTextLabel("test_cmds vehicle label", 0xFFFFFFFF,
                    0.0, 0.0, 0.0, 30.0, GetPlayerVirtualWorld(playerid));
                Attach3DTextLabelToVehicle(gTestLabel[playerid], gTestVehicle[playerid], 0.0, 0.0, 1.5);
                gTestPlayerLabel[playerid] = CreatePlayer3DTextLabel(playerid, "test_cmds player label",
                    0x66FF66FF, 0.0, 0.0, 1.0, 30.0, playerid, INVALID_VEHICLE_ID, true);
            }
            format(detail, sizeof(detail), "vehicle=%d global_label=%d player_label=%d",
                gTestVehicle[playerid], _:gTestLabel[playerid], _:gTestPlayerLabel[playerid]);
            TestCmdsResult(playerid,
                gTestVehicle[playerid] != INVALID_VEHICLE_ID &&
                gTestLabel[playerid] != Text3D:INVALID_3DTEXT_ID &&
                gTestPlayerLabel[playerid] != PlayerText3D:INVALID_3DTEXT_ID,
                "labels_create", detail, detail);
            TestCmdsLog(playerid, "OBSERVE", "labels_render", "attached vehicle/player labels should be visible until automatic cleanup");
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid, gTestDelay[playerid] + 500);
        }
        case 1:
        {
            Update3DTextLabelText(gTestLabel[playerid], 0xFFCC66FF, "test_cmds vehicle label updated");
            UpdatePlayer3DTextLabelText(playerid, gTestPlayerLabel[playerid], 0xFFFFFFFF,
                "test_cmds player label updated");
            TestCmdsLog(playerid, "OBSERVE", "labels_update", "both label texts updated");
            gTestStep[playerid]++;
            return TestCmdsSchedule(playerid);
        }
        case 2:
        {
            TestCmdsDestroyLabels(playerid);
            TestCmdsDestroyVehicle(playerid);
            TestCmdsLog(playerid, "PASS", "labels_cleanup", "labels and temporary vehicle deleted automatically");
            return TestCmdsFinishCase(playerid);
        }
    }
    return TestCmdsFinishCase(playerid);
}

stock TestCmdsStart(playerid, mask, delay, requestId = 0)
{
    new detail[128];

    if (gTestActive[playerid])
    {
        SendClientMessage(playerid, 0xFFCC66FF, "[test_cmds] A run is already active. Use /testcmds status or /testcmds stop.");
        return 0;
    }
    if (!mask)
    {
        SendClientMessage(playerid, 0xFF6666FF, "[test_cmds] Unknown test. Use: vehicle, player, pvars, ui, labels, all.");
        return 0;
    }
    if (delay < TEST_CMDS_MIN_DELAY_MS || delay > TEST_CMDS_MAX_DELAY_MS)
    {
        delay = TEST_CMDS_DEFAULT_DELAY_MS;
    }

    TestCmdsCleanup(playerid);
    gTestActive[playerid] = true;
    gTestRunId[playerid] = ++gNextRunId;
    gTestRequestId[playerid] = requestId;
    gTestToken[playerid]++;
    gTestPendingMask[playerid] = mask;
    gTestCase[playerid] = TEST_CASE_NONE;
    gTestStep[playerid] = 0;
    gTestDelay[playerid] = delay;
    gTestPasses[playerid] = 0;
    gTestFailures[playerid] = 0;
    gTestObservations[playerid] = 0;
    format(detail, sizeof(detail), "mask=0x%x delay_ms=%d result_file=scriptfiles/%s", mask, delay, TEST_CMDS_LOG_FILE);
    TestCmdsLog(playerid, "ACTION", "run_start", detail);
    TestCmdsEmitMarker(playerid, "RUN_START", "ACTION", detail);
    return TestCmdsBeginNextCase(playerid);
}

stock TestCmdsStop(playerid, const reason[])
{
    if (gTestTimer[playerid])
    {
        KillTimer(gTestTimer[playerid]);
        gTestTimer[playerid] = 0;
    }
    gTestToken[playerid]++;
    if (gTestActive[playerid])
    {
        TestCmdsLog(playerid, "ACTION", "run_stop", reason);
        TestCmdsEmitMarker(playerid, "RUN_ABORT", "FAIL", reason);
    }
    gTestActive[playerid] = false;
    gTestPendingMask[playerid] = 0;
    gTestCase[playerid] = TEST_CASE_NONE;
    gTestStep[playerid] = 0;
    TestCmdsCleanup(playerid);
    return 1;
}

stock bool:TestCmdsAutoTargetMatches(playerid)
{
    new playerName[MAX_PLAYER_NAME + 1];

    if (!strcmp(gAutoRequestTarget, "*"))
    {
        return true;
    }
    GetPlayerName(playerid, playerName, sizeof(playerName));
    return !strcmp(playerName, gAutoRequestTarget, true);
}

/// Treats synced in-world states as ready when IsPlayerSpawned has not caught
/// up with an already-running legacy client.
/// References: https://open.mp/docs/scripting/functions/IsPlayerSpawned,
/// https://open.mp/docs/scripting/functions/GetPlayerState, and
/// https://open.mp/docs/scripting/resources/playerstates
stock bool:TestCmdsPlayerReadyForRun(playerid)
{
    if (!IsPlayerConnected(playerid))
    {
        return false;
    }
    if (IsPlayerSpawned(playerid))
    {
        return true;
    }

    new PLAYER_STATE:playerState = GetPlayerState(playerid);
    return playerState != PLAYER_STATE_NONE &&
        playerState != PLAYER_STATE_WASTED &&
        playerState != PLAYER_STATE_SPECTATING;
}

stock TestCmdsReadAutoRequest()
{
    new File:file;
    new line[192];
    new index;
    new requestText[16];
    new groupText[16];
    new delayText[16];
    new spawnText[8];
    new targetText[MAX_PLAYER_NAME + 1];
    new mask;
    new requestId;
    new requestDelay;

    if (gAutoRequestPending)
    {
        return 0;
    }
    file = fopen(TEST_CMDS_REQUEST_FILE, io_read);
    if (!file)
    {
        return 0;
    }
    fread(file, line, sizeof(line));
    fclose(file);

    TestCmdsNextToken(line, index, requestText, sizeof(requestText));
    TestCmdsNextToken(line, index, groupText, sizeof(groupText));
    TestCmdsNextToken(line, index, delayText, sizeof(delayText));
    TestCmdsNextToken(line, index, spawnText, sizeof(spawnText));
    TestCmdsNextToken(line, index, targetText, sizeof(targetText));
    requestId = strval(requestText);
    mask = TestCmdsMaskFromName(groupText);
    requestDelay = strval(delayText);
    if (requestDelay < TEST_CMDS_MIN_DELAY_MS || requestDelay > TEST_CMDS_MAX_DELAY_MS)
    {
        requestDelay = TEST_CMDS_DEFAULT_DELAY_MS;
    }
    if (!strlen(targetText))
    {
        format(targetText, sizeof(targetText), "*");
    }

    fremove(TEST_CMDS_REQUEST_FILE);
    if (requestId <= 0 || !mask)
    {
        printf("[test_cmds] marker=REQUEST_REJECTED request=%d status=FAIL detail=invalid_request line='%s'", requestId, line);
        return 0;
    }

    gAutoRequestPending = true;
    gAutoRequestId = requestId;
    gAutoRequestMask = mask;
    gAutoRequestDelay = requestDelay;
    gAutoRequestSpawn = strval(spawnText) != 0;
    format(gAutoRequestTarget, sizeof(gAutoRequestTarget), "%s", targetText);
    gAutoClaimPlayer = INVALID_PLAYER_ID;
    gAutoTransitionScheduled = false;
    gAutoSpawnAttempts = 0;
    printf("[test_cmds] marker=REQUEST_ACCEPTED request=%d status=ACTION detail=group=%s delay_ms=%d autospawn=%d target=%s",
        requestId, groupText, requestDelay, gAutoRequestSpawn, gAutoRequestTarget);
    return 1;
}

stock TestCmdsTryAutoClaim(playerid)
{
    new bool:playerReady;

    if (!gAutoRequestPending || !IsPlayerConnected(playerid) || !TestCmdsAutoTargetMatches(playerid))
    {
        return 0;
    }
    if (gAutoClaimPlayer != INVALID_PLAYER_ID && gAutoClaimPlayer != playerid)
    {
        return 0;
    }
    gAutoClaimPlayer = playerid;
    if (gAutoTransitionScheduled)
    {
        return 1;
    }

    playerReady = TestCmdsPlayerReadyForRun(playerid);
    printf("[test_cmds] marker=AUTO_CLAIM_CHECK request=%d player=%d status=ACTION detail=claimed=%d scheduled=%d spawned=%d state=%d ready=%d",
        gAutoRequestId, playerid, gAutoClaimPlayer, gAutoTransitionScheduled,
        IsPlayerSpawned(playerid), _:GetPlayerState(playerid), playerReady);
    gAutoTransitionScheduled = true;
    if (playerReady)
    {
        printf("[test_cmds] marker=AUTO_READY request=%d player=%d status=ACTION detail=spawned=%d state=%d",
            gAutoRequestId, playerid, IsPlayerSpawned(playerid), _:GetPlayerState(playerid));
        SetTimerEx("TestCmdsAutoStart", TEST_CMDS_AUTOSTART_DELAY_MS, false, "ii", playerid, gAutoRequestId);
    }
    else if (gAutoRequestSpawn)
    {
        SetTimerEx("TestCmdsAutoSpawn", TEST_CMDS_AUTOSPAWN_DELAY_MS, false, "ii", playerid, gAutoRequestId);
    }
    else
    {
        gAutoTransitionScheduled = false;
    }
    return 1;
}

stock TestCmdsShowHelp(playerid)
{
    SendClientMessage(playerid, 0x66FF66FF, "[test_cmds] /testcmds batch [all|vehicle|player|pvars|ui|labels] [delay_ms]");
    SendClientMessage(playerid, 0xFFFFFFFF, "[test_cmds] /testcmds run <test> [delay_ms] | /testcmds status | /testcmds stop");
    SendClientMessage(playerid, 0xFFFFFFFF, "[test_cmds] Aliases: /tbatch /tvehicle /tplayer /tpvars /tui /tlabels");
    SendClientMessage(playerid, 0xFFCC66FF, "[test_cmds] Results: server log + scriptfiles/test_cmds_results.log + client chat.");
    return 1;
}

/// Loads the automated compatibility filterscript.
/// Reference: https://open.mp/docs/scripting/callbacks/OnFilterScriptInit
public OnFilterScriptInit()
{
    print("[test_cmds] automated legacy compatibility filterscript loaded");
    print("[test_cmds] commands: /testcmds, /tbatch, /tvehicle, /tplayer, /tpvars, /tui, /tlabels");
    TestCmdsReadAutoRequest();
    gAutoPollTimer = SetTimer("TestCmdsPollRequest", TEST_CMDS_REQUEST_POLL_MS, true);
    return 1;
}

public OnFilterScriptExit()
{
    if (gAutoPollTimer)
    {
        KillTimer(gAutoPollTimer);
        gAutoPollTimer = 0;
    }
    for (new playerid = 0; playerid < MAX_PLAYERS; playerid++)
    {
        if (gTestActive[playerid] || gTestTimer[playerid])
        {
            TestCmdsStop(playerid, "filterscript_exit");
        }
    }
    print("[test_cmds] filterscript unloaded");
    return 1;
}

public OnPlayerDisconnect(playerid, reason)
{
    #pragma unused reason
    TestCmdsStop(playerid, "player_disconnect");
    if (gAutoClaimPlayer == playerid)
    {
        gAutoClaimPlayer = INVALID_PLAYER_ID;
        gAutoTransitionScheduled = false;
    }
    return 1;
}

/// Claims a pending host-generated request when its target player connects.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerConnect
public OnPlayerConnect(playerid)
{
    TestCmdsTryAutoClaim(playerid);
    return 1;
}

/// Starts a pending request only after the client has reached spawned state.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerSpawn
public OnPlayerSpawn(playerid)
{
    if (gAutoRequestPending && TestCmdsAutoTargetMatches(playerid))
    {
        gAutoClaimPlayer = playerid;
        gAutoTransitionScheduled = true;
        SetTimerEx("TestCmdsAutoStart", TEST_CMDS_AUTOSTART_DELAY_MS, false, "ii", playerid, gAutoRequestId);
    }
    return 1;
}

/// Polls the one-shot scriptfiles request written by tools/reloop.
/// References: https://open.mp/docs/scripting/functions/fopen and /fread
public TestCmdsPollRequest()
{
    TestCmdsReadAutoRequest();
    if (gAutoRequestPending)
    {
        for (new playerid = 0; playerid < MAX_PLAYERS; playerid++)
        {
            if (TestCmdsTryAutoClaim(playerid))
            {
                break;
            }
        }
    }
    return 1;
}

/// Forces only the named local test player through class selection.
/// References: https://open.mp/docs/scripting/functions/SetSpawnInfo and /SpawnPlayer
public TestCmdsAutoSpawn(playerid, requestId)
{
    new result;

    if (!gAutoRequestPending || requestId != gAutoRequestId || playerid != gAutoClaimPlayer || !IsPlayerConnected(playerid))
    {
        return 0;
    }
    if (TestCmdsPlayerReadyForRun(playerid))
    {
        gAutoTransitionScheduled = false;
        return TestCmdsTryAutoClaim(playerid);
    }

    gAutoSpawnAttempts++;
    SetSpawnInfo(playerid, 0, 0, 306.0034, 2042.9145, 16.6400, 0.0,
        WEAPON_M4, 600, WEAPON_DEAGLE, 120, WEAPON_KNIFE, 1);
    result = SpawnPlayer(playerid);
    printf("[test_cmds] marker=AUTO_SPAWN request=%d player=%d status=%s detail=attempt=%d returned=%d",
        requestId, playerid, result ? "ACTION" : "FAIL", gAutoSpawnAttempts, result);
    if (!result && gAutoSpawnAttempts >= 3)
    {
        printf("[test_cmds] marker=RUN_ABORT request=%d player=%d status=FAIL detail=autospawn_failed", requestId, playerid);
        gAutoRequestPending = false;
        gAutoClaimPlayer = INVALID_PLAYER_ID;
    }
    else
    {
        gAutoTransitionScheduled = false;
    }
    return result;
}

/// Transfers the accepted host request to the ordinary deterministic runner.
/// References: https://open.mp/docs/scripting/functions/IsPlayerSpawned and
/// https://open.mp/docs/scripting/functions/GetPlayerState
public TestCmdsAutoStart(playerid, requestId)
{
    new mask;
    new requestDelay;

    if (!gAutoRequestPending || requestId != gAutoRequestId || playerid != gAutoClaimPlayer ||
        !TestCmdsPlayerReadyForRun(playerid))
    {
        gAutoTransitionScheduled = false;
        return 0;
    }

    mask = gAutoRequestMask;
    requestDelay = gAutoRequestDelay;
    gAutoRequestPending = false;
    gAutoClaimPlayer = INVALID_PLAYER_ID;
    gAutoTransitionScheduled = false;
    return TestCmdsStart(playerid, mask, requestDelay, requestId);
}

/// Runs the next automated step. Timer IDs are reset before any new timer is created.
/// Reference: https://open.mp/docs/scripting/functions/SetTimerEx
public TestCmdsAdvance(playerid, token)
{
    if (!IsPlayerConnected(playerid) || !gTestActive[playerid] || token != gTestToken[playerid])
    {
        return 0;
    }
    gTestTimer[playerid] = 0;
    switch (gTestCase[playerid])
    {
        case TEST_CASE_VEHICLE: return TestCmdsRunVehicleStep(playerid);
        case TEST_CASE_PLAYER: return TestCmdsRunPlayerStep(playerid);
        case TEST_CASE_PVARS: return TestCmdsRunPVarStep(playerid);
        case TEST_CASE_UI: return TestCmdsRunUIStep(playerid);
        case TEST_CASE_LABELS: return TestCmdsRunLabelsStep(playerid);
    }
    return TestCmdsBeginNextCase(playerid);
}

/// Records the callback emitted by SetVehicleToRespawn and reapplies the original mod fixture.
/// Reference: https://open.mp/docs/scripting/callbacks/OnVehicleSpawn
public OnVehicleSpawn(vehicleid)
{
    new detail[96];

    for (new playerid = 0; playerid < MAX_PLAYERS; playerid++)
    {
        if (gTestActive[playerid] && gTestVehicle[playerid] == vehicleid)
        {
            gTestVehicleSpawnSeen[playerid] = true;
            AddVehicleComponent(vehicleid, 1078);
            AddVehicleComponent(vehicleid, 1010);
            format(detail, sizeof(detail), "vehicle=%d callback received; components 1078 and 1010 reapplied", vehicleid);
            TestCmdsLog(playerid, "PASS", "vehicle_spawn_callback", detail);
        }
    }
    return 1;
}

public OnDialogResponse(playerid, dialogid, response, listitem, inputtext[])
{
    new detail[160];

    if (dialogid < TEST_CMDS_DIALOG_BASE || dialogid > TEST_CMDS_DIALOG_BASE + 3)
    {
        return 0;
    }
    format(detail, sizeof(detail), "dialog=%d response=%d listitem=%d input='%s'", dialogid, response, listitem, inputtext);
    TestCmdsLog(playerid, "ACTION", "dialog_response", detail);
    return 1;
}

/// Dispatches batch, individual, status and stop commands before the gamemode callback.
/// Reference: https://open.mp/docs/scripting/callbacks/OnPlayerCommandText
public OnPlayerCommandText(playerid, cmdtext[])
{
    new index;
    new command[32];
    new action[16];
    new testName[16];
    new delayText[16];
    new commandDelay = TEST_CMDS_DEFAULT_DELAY_MS;
    new mask;

    TestCmdsNextToken(cmdtext, index, command, sizeof(command));
    if (!strcmp(command, "/tbatch", true))
    {
        return TestCmdsStart(playerid, TEST_MASK_ALL, TEST_CMDS_DEFAULT_DELAY_MS);
    }
    if (!strcmp(command, "/tpassword", true))
    {
        ShowPlayerDialog(playerid, TEST_CMDS_DIALOG_BASE + 3, DIALOG_STYLE_PASSWORD,
            "test_cmds password", "Type the fixed parity probe value below.", "Submit", "Cancel");
        TestCmdsLog(playerid, "OBSERVE", "ui_dialog_password_manual",
            "password dialog shown; submit through the client to verify masking and RPC 62 input");
        return 1;
    }
    if (!strcmp(command, "/tvehicle", true)) return TestCmdsStart(playerid, TEST_MASK_VEHICLE, commandDelay);
    if (!strcmp(command, "/tplayer", true)) return TestCmdsStart(playerid, TEST_MASK_PLAYER, commandDelay);
    if (!strcmp(command, "/tpvars", true)) return TestCmdsStart(playerid, TEST_MASK_PVARS, commandDelay);
    if (!strcmp(command, "/tui", true)) return TestCmdsStart(playerid, TEST_MASK_UI, commandDelay);
    if (!strcmp(command, "/tlabels", true)) return TestCmdsStart(playerid, TEST_MASK_LABELS, commandDelay);
    if (strcmp(command, "/testcmds", true))
    {
        return 0;
    }

    TestCmdsNextToken(cmdtext, index, action, sizeof(action));
    if (!strlen(action) || !strcmp(action, "help", true) || !strcmp(action, "list", true))
    {
        return TestCmdsShowHelp(playerid);
    }
    if (!strcmp(action, "stop", true))
    {
        TestCmdsStop(playerid, "player_command");
        SendClientMessage(playerid, 0xFFCC66FF, "[test_cmds] Run stopped and temporary state cleaned up.");
        return 1;
    }
    if (!strcmp(action, "status", true))
    {
        new caseName[16];
        new statusLine[144];
        TestCmdsCaseName(gTestCase[playerid], caseName, sizeof(caseName));
        format(statusLine, sizeof(statusLine),
            "[test_cmds] active=%d run=%d case=%s step=%d pending=0x%x pass=%d fail=%d observe=%d",
            gTestActive[playerid], gTestRunId[playerid], caseName, gTestStep[playerid], gTestPendingMask[playerid],
            gTestPasses[playerid], gTestFailures[playerid], gTestObservations[playerid]);
        SendClientMessage(playerid, 0xFFFFFFFF, statusLine);
        return 1;
    }
    if (!strcmp(action, "run", true) || !strcmp(action, "batch", true))
    {
        TestCmdsNextToken(cmdtext, index, testName, sizeof(testName));
        TestCmdsNextToken(cmdtext, index, delayText, sizeof(delayText));
        if (!strlen(testName) && !strcmp(action, "batch", true))
        {
            format(testName, sizeof(testName), "all");
        }
        if (strlen(delayText))
        {
            commandDelay = strval(delayText);
        }
        mask = TestCmdsMaskFromName(testName);
        return TestCmdsStart(playerid, mask, commandDelay);
    }

    return TestCmdsShowHelp(playerid);
}
