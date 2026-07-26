// STATIC_037 focused metadata export for the SA-MP 0.3.7-R5 remote
// ProcessControl/UseGun input-context path. Emits instruction, call and data
// reference metadata only; no decompiler pseudocode.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;
import java.util.LinkedHashSet;
import java.util.Set;

public class InspectCombatContext extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;
    private static final long PLAYER_PED_TABLE = 0x1026bf10L;
    private static final int PLAYER_PED_TABLE_SLOTS = 210;
    private static final long[] FOCUS_FUNCTIONS = new long[] {
        0x100a2960L, // CPlayerPed::ProcessControl replacement
        0x100a2de0L, // CTaskSimpleUseGun::SetPedPosition replacement
        0x100af340L, // CPlayerPed::SetKeys
        0x100b4320L, // register GTA CPlayerPed pointer for player slot
        0x100b4360L, // resolve SA-MP player index from GTA ped
        0x100a72c0L, // store local keys
        0x100a7360L, // install remote keys
        0x100a7300L, // restore local keys
        0x1009c7c0L, // store local camera zoom
        0x1009c7e0L, // restore local camera zoom
        0x1009c8b0L, // get remote camera mode
        0x1009c850L, // install remote camera zoom
        0x1009c940L, // store local aim
        0x1009c9c0L, // install remote aim
        0x1009c960L, // restore local aim
        0x1009cb30L, // store local weapon skills
        0x1009cd20L, // install remote weapon skills
        0x1009cbc0L  // restore local weapon skills
    };

    private File outDir;

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException(
                "usage: InspectCombatContext.java <output-dir>");
        }
        outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());
        exportMetadata();
        exportPlayerPedTableReferences();
    }

    private void exportMetadata() throws Exception {
        BufferedWriter functions = writer("functions.tsv");
        BufferedWriter instructions = writer("instructions.tsv");
        BufferedWriter references = writer("references.tsv");
        BufferedWriter incoming = writer("incoming.tsv");

        functions.write(
            "requested_rva\tentry_rva\tname\tsize\tcalling_convention\n");
        instructions.write(
            "function_rva\tinstruction_rva\tbytes\tmnemonic\tinstruction\n");
        references.write(
            "function_rva\tinstruction_rva\tref_type\ttarget\ttarget_rva\t"
                + "target_function\ttarget_function_rva\n");
        incoming.write(
            "function_rva\tfrom_rva\tref_type\tfrom_function\t"
                + "from_function_rva\n");

        for (long requested : FOCUS_FUNCTIONS) {
            Address requestedAddress = toAddr(requested);
            Function function = getFunctionContaining(requestedAddress);
            if (function == null) {
                /*
                 * STATIC_037:
                 * The two naked hook bodies are installed through data writes,
                 * so normal call-based discovery can leave them undefined.
                 * Their entry RVAs come directly from the guarded installer at
                 * samp.dll+0xA62E0. Define only those explicit entry points.
                 */
                disassemble(requestedAddress);
                function = createFunction(
                    requestedAddress,
                    String.format("focus_%08x", requested - IMAGE_BASE));
            }
            if (function == null) {
                functions.write(tsv(rva(requested), "", "missing", 0, ""));
                continue;
            }
            long entry = function.getEntryPoint().getOffset();
            functions.write(tsv(
                rva(requested), rva(entry), function.getName(),
                function.getBody().getNumAddresses(),
                function.getCallingConventionName()));

            ReferenceIterator incomingRefs =
                currentProgram.getReferenceManager().getReferencesTo(
                    function.getEntryPoint());
            while (incomingRefs.hasNext() && !monitor.isCancelled()) {
                Reference ref = incomingRefs.next();
                Function from = getFunctionContaining(ref.getFromAddress());
                incoming.write(tsv(
                    rva(entry), rva(ref.getFromAddress().getOffset()),
                    ref.getReferenceType(), from == null ? "" : from.getName(),
                    from == null ? "" : rva(from.getEntryPoint().getOffset())));
            }

            InstructionIterator iterator =
                currentProgram.getListing().getInstructions(
                    function.getBody(), true);
            while (iterator.hasNext() && !monitor.isCancelled()) {
                Instruction instruction = iterator.next();
                instructions.write(tsv(
                    rva(entry), rva(instruction.getAddress().getOffset()),
                    hex(instruction.getBytes()), instruction.getMnemonicString(),
                    instruction));
                for (Reference ref : instruction.getReferencesFrom()) {
                    Function target = getFunctionContaining(ref.getToAddress());
                    references.write(tsv(
                        rva(entry), rva(instruction.getAddress().getOffset()),
                        ref.getReferenceType(), ref.getToAddress(),
                        rva(ref.getToAddress().getOffset()),
                        target == null ? "" : target.getName(),
                        target == null
                            ? ""
                            : rva(target.getEntryPoint().getOffset())));
                }
            }
        }

        functions.close();
        instructions.close();
        references.close();
        incoming.close();
    }

    private void exportPlayerPedTableReferences() throws Exception {
        BufferedWriter refs = writer("player_ped_table_references.tsv");
        BufferedWriter functions =
            writer("player_ped_table_functions.tsv");
        BufferedWriter instructions =
            writer("player_ped_table_instructions.tsv");
        Set<Long> functionEntries = new LinkedHashSet<Long>();

        refs.write(
            "table_target_rva\tfrom_rva\tref_type\tinstruction\t"
                + "from_function\tfrom_function_rva\n");
        /*
         * STATIC_037:
         * samp.dll+0x26BF10 is the 210-entry GTA CPlayerPed pointer record
         * scanned by samp.dll+0xB4360. Enumerating the entire bounded table
         * catches both fixed-slot references and the indexed base reference.
         */
        for (int offset = 0;
             offset < PLAYER_PED_TABLE_SLOTS * Integer.BYTES;
             offset++) {
            Address target = toAddr(PLAYER_PED_TABLE + offset);
            ReferenceIterator iterator =
                currentProgram.getReferenceManager().getReferencesTo(target);
            while (iterator.hasNext() && !monitor.isCancelled()) {
                Reference ref = iterator.next();
                Function from =
                    getFunctionContaining(ref.getFromAddress());
                Instruction instruction =
                    getInstructionAt(ref.getFromAddress());
                refs.write(tsv(
                    rva(target.getOffset()),
                    rva(ref.getFromAddress().getOffset()),
                    ref.getReferenceType(),
                    instruction == null ? "" : instruction,
                    from == null ? "" : from.getName(),
                    from == null
                        ? ""
                        : rva(from.getEntryPoint().getOffset())));
                if (from != null) {
                    functionEntries.add(from.getEntryPoint().getOffset());
                }
            }
        }
        refs.close();

        functions.write(
            "entry_rva\tname\tsize\tcalling_convention\n");
        instructions.write(
            "function_rva\tinstruction_rva\tbytes\tmnemonic\tinstruction\n");
        for (long entry : functionEntries) {
            Function function = getFunctionAt(toAddr(entry));
            if (function == null) {
                continue;
            }
            functions.write(tsv(
                rva(entry), function.getName(),
                function.getBody().getNumAddresses(),
                function.getCallingConventionName()));
            InstructionIterator iterator =
                currentProgram.getListing().getInstructions(
                    function.getBody(), true);
            while (iterator.hasNext() && !monitor.isCancelled()) {
                Instruction instruction = iterator.next();
                instructions.write(tsv(
                    rva(entry), rva(instruction.getAddress().getOffset()),
                    hex(instruction.getBytes()),
                    instruction.getMnemonicString(), instruction));
            }
        }
        functions.close();
        instructions.close();
    }

    private BufferedWriter writer(String name) throws Exception {
        return new BufferedWriter(new FileWriter(new File(outDir, name)));
    }

    private String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            result.append(String.format("%02x", value & 0xff));
        }
        return result.toString();
    }

    private String tsv(Object... columns) {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < columns.length; index++) {
            if (index > 0) {
                result.append('\t');
            }
            result.append(String.valueOf(columns[index])
                .replace("\t", " ")
                .replace("\n", "\\n"));
        }
        result.append('\n');
        return result.toString();
    }

    private String rva(long address) {
        if (address < IMAGE_BASE || address >= 0x20000000L) {
            return String.format("external:0x%08x", address);
        }
        return String.format("0x%08x", address - IMAGE_BASE);
    }
}
