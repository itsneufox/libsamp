// STATIC_037 focused metadata export for SA-MP camera/spawn path triage.
// This script intentionally emits compact call/data/reference metadata only.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class InspectCameraSpawnPaths extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;
    private File outDir;

    private static final long[] FOCUS_FUNCTIONS = new long[] {
        0x1009e8a0L, // string xrefs: CreateObject/CreateVehicle/SetPlayerCameraPos/LookAt registration area
        0x1009e4b0L, // helper reached by multiple script native name branches
        0x1009e500L,
        0x1009e610L,
        0x1009e720L, // SetPlayerCameraLookAt branch target candidate
        0x1009e790L,
        0x1009e850L,
        0x100c5620L, // string xrefs: Spawn UI area
        0x10003730L, // GetTickCount-heavy runtime/update loop candidate
        0x10060160L, // State Information/Ped Context diagnostic string
        0x100b3e20L,
        0x100a9650L,
        0x100a9bd0L
    };

    private static final Set<Long> FOCUS_CONSTANTS = new HashSet<Long>(Arrays.asList(
        0x00b6f1a8L, // GTA camera_mode observed by ASI probe
        0x00b6f858L, // GTA camera_mode2 observed by ASI probe
        0x0053bfc8L, // CTheScripts::Process callsite observed by ASI probe/replacement hook
        0x0046a000L, // original CTheScripts::Process target observed by ASI probe
        0x0053e230L, // graphics loop target observed by ASI probe
        0x0053bed1L, // process storage/hook area used by replacement
        0x0000015aL, // restore_camera opcode
        0x0000015fL, // set_camera_position opcode
        0x00000160L, // point_camera opcode
        0x000002ebL, // restore_camera_jumpcut opcode
        0x00000373L  // set_camera_behind_player opcode
    ));

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException("usage: InspectCameraSpawnPaths.java <output-dir>");
        }
        outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());

        exportFunctionSummaries();
        exportFocusConstantRefs();
        exportStringReferenceNeighborhoods();
    }

    private void exportFunctionSummaries() throws Exception {
        BufferedWriter w = writer("camera_spawn_function_summaries.tsv");
        w.write("function\tfunction_rva\tsize\tcall_out\tdata_refs_from\tcallsite_rva\ttarget\ttarget_rva\tref_type\n");
        for (long addrValue : FOCUS_FUNCTIONS) {
            Function f = getFunctionContaining(toAddr(addrValue));
            if (f == null) {
                w.write("missing\t" + rva(addrValue) + "\t0\t0\t0\t\t\t\t\n");
                continue;
            }
            int calls = 0;
            int dataRefs = 0;
            InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
            while (it.hasNext() && !monitor.isCancelled()) {
                Instruction insn = it.next();
                for (Reference ref : insn.getReferencesFrom()) {
                    if (ref.getReferenceType().isCall()) {
                        calls++;
                    } else if (ref.getReferenceType().isData()) {
                        dataRefs++;
                    }
                }
            }
            it = currentProgram.getListing().getInstructions(f.getBody(), true);
            while (it.hasNext() && !monitor.isCancelled()) {
                Instruction insn = it.next();
                for (Reference ref : insn.getReferencesFrom()) {
                    if (!ref.getReferenceType().isCall()) {
                        continue;
                    }
                    Function target = getFunctionContaining(ref.getToAddress());
                    w.write(tsv(f.getName(), rva(f.getEntryPoint().getOffset()), f.getBody().getNumAddresses(), calls,
                        dataRefs, rva(insn.getAddress().getOffset()), target == null ? ref.getToAddress().toString() : target.getName(),
                        rva(ref.getToAddress().getOffset()), ref.getReferenceType().toString()));
                }
            }
        }
        w.close();
    }

    private void exportFocusConstantRefs() throws Exception {
        BufferedWriter w = writer("camera_spawn_focus_constant_refs.tsv");
        w.write("function\tfunction_rva\tinsn_rva\tmnemonic\tconstant\toperand_index\toperand\n");
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction insn = it.next();
            for (int op = 0; op < insn.getNumOperands(); op++) {
                Object[] objects = insn.getOpObjects(op);
                for (Object object : objects) {
                    if (!(object instanceof Scalar)) {
                        continue;
                    }
                    long value = ((Scalar)object).getUnsignedValue();
                    if (!FOCUS_CONSTANTS.contains(value)) {
                        continue;
                    }
                    Function f = getFunctionContaining(insn.getAddress());
                    w.write(tsv(f == null ? "" : f.getName(), f == null ? "" : rva(f.getEntryPoint().getOffset()),
                        rva(insn.getAddress().getOffset()), insn.getMnemonicString(), hex(value), op,
                        insn.getDefaultOperandRepresentation(op)));
                }
            }
        }
        w.close();
    }

    private void exportStringReferenceNeighborhoods() throws Exception {
        BufferedWriter w = writer("camera_spawn_string_ref_neighborhoods.tsv");
        w.write("string\tstring_rva\tfunction\tfunction_rva\tref_rva\tinsn_rva\tmnemonic\toperand0\toperand1\n");
        String[] needles = new String[] {
            "SetPlayerCameraPos",
            "SetPlayerCameraLookAt",
            "Spawn",
            "Camera",
            "Joypad: %d LocalContext: %u UpdateCameraAim: %f %f %f"
        };
        for (String needle : needles) {
            Address stringAddress = findStringAddress(needle);
            if (stringAddress == null) {
                w.write(needle + "\tmissing\t\t\t\t\t\t\t\n");
                continue;
            }
            ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(stringAddress);
            while (refs.hasNext() && !monitor.isCancelled()) {
                Reference ref = refs.next();
                Function f = getFunctionContaining(ref.getFromAddress());
                for (int delta = -4; delta <= 4; delta++) {
                    Instruction insn = instructionNear(ref.getFromAddress(), delta);
                    if (insn == null) {
                        continue;
                    }
                    w.write(tsv(needle, rva(stringAddress.getOffset()), f == null ? "" : f.getName(),
                        f == null ? "" : rva(f.getEntryPoint().getOffset()), rva(ref.getFromAddress().getOffset()),
                        rva(insn.getAddress().getOffset()), insn.getMnemonicString(), operand(insn, 0), operand(insn, 1)));
                }
            }
        }
        w.close();
    }

    private Address findStringAddress(String needle) {
        var it = currentProgram.getListing().getDefinedData(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            var data = it.next();
            Object value = data.getValue();
            if (value != null && needle.equals(String.valueOf(value))) {
                return data.getAddress();
            }
        }
        return null;
    }

    private Instruction instructionNear(Address address, int delta) {
        Instruction insn = currentProgram.getListing().getInstructionContaining(address);
        if (insn == null) {
            insn = currentProgram.getListing().getInstructionBefore(address);
        }
        while (insn != null && delta < 0) {
            insn = currentProgram.getListing().getInstructionBefore(insn.getAddress());
            delta++;
        }
        while (insn != null && delta > 0) {
            insn = currentProgram.getListing().getInstructionAfter(insn.getAddress());
            delta--;
        }
        return insn;
    }

    private String operand(Instruction insn, int index) {
        if (index >= insn.getNumOperands()) {
            return "";
        }
        return insn.getDefaultOperandRepresentation(index);
    }

    private BufferedWriter writer(String name) throws Exception {
        return new BufferedWriter(new FileWriter(new File(outDir, name)));
    }

    private String tsv(Object... cols) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < cols.length; i++) {
            if (i > 0) {
                sb.append('\t');
            }
            sb.append(String.valueOf(cols[i]).replace("\t", " ").replace("\n", "\\n"));
        }
        sb.append('\n');
        return sb.toString();
    }

    private String rva(long address) {
        return String.format("0x%08x", address - IMAGE_BASE);
    }

    private String hex(long value) {
        return String.format("0x%08x", value);
    }
}
