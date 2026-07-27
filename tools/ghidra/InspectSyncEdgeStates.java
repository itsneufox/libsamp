// STATIC_037 focused metadata export for SA-MP 0.3.7-R5 edge-state sync.
// Emits bounded instruction/reference/scalar metadata only; no decompiler
// pseudocode.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;

public class InspectSyncEdgeStates extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;

    private static final Focus[] FOCUS = new Focus[] {
        new Focus("update_surfing", 0x10003730L),
        new Focus("send_unoccupied_sync", 0x10004d30L),
        new Focus("send_trailer_sync", 0x100053d0L),
        new Focus("send_passenger_sync", 0x10005590L),
        new Focus("process_spectating", 0x10006540L),
        new Focus("process_unoccupied", 0x10006e00L),
        new Focus("send_incar_sync", 0x10007080L),
        new Focus("camera_get_matrix", 0x1009d460L),
        new Focus("camera_ctor", 0x1009ff60L)
    };

    private File outDir;

    private static class Focus {
        final String label;
        final long address;

        Focus(String label, long address) {
            this.label = label;
            this.address = address;
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException(
                "usage: InspectSyncEdgeStates.java <output-dir>");
        }
        outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());
        exportIdentity();
        exportMetadata();
        exportFocusMemory();
    }

    private void exportIdentity() throws Exception {
        BufferedWriter out = writer("identity.tsv");
        out.write("property\tvalue\n");
        out.write(tsv("program_name", currentProgram.getName()));
        out.write(tsv("executable_path", currentProgram.getExecutablePath()));
        out.write(tsv("executable_format", currentProgram.getExecutableFormat()));
        out.write(tsv("executable_md5", currentProgram.getExecutableMD5()));
        out.write(tsv("executable_sha256", currentProgram.getExecutableSHA256()));
        out.write(tsv("image_base", currentProgram.getImageBase()));
        out.write(tsv("language_id", currentProgram.getLanguageID()));
        out.close();
    }

    private void exportMetadata() throws Exception {
        BufferedWriter functions = writer("functions.tsv");
        BufferedWriter instructions = writer("instructions.tsv");
        BufferedWriter references = writer("references.tsv");
        BufferedWriter scalars = writer("scalars.tsv");

        functions.write(
            "label\trequested_rva\tentry_rva\tname\tsize\tinstruction_count"
                + "\tcalling_convention\tentry_bytes_16\n");
        instructions.write(
            "label\tfunction_rva\tinsn_rva\tbytes\tmnemonic\tinstruction"
                + "\tflow_type\n");
        references.write(
            "label\tfunction_rva\tinsn_rva\tref_type\ttarget\ttarget_rva"
                + "\ttarget_function\ttarget_function_rva\n");
        scalars.write(
            "label\tfunction_rva\tinsn_rva\tmnemonic\toperand_index\tvalue"
                + "\toperand\n");

        for (Focus focus : FOCUS) {
            Function function = getFunctionContaining(toAddr(focus.address));
            if (function == null) {
                functions.write(tsv(
                    focus.label, rva(focus.address), "", "missing", 0, 0,
                    "", ""));
                continue;
            }

            int instructionCount = 0;
            InstructionIterator iterator =
                currentProgram.getListing().getInstructions(
                    function.getBody(), true);
            while (iterator.hasNext() && !monitor.isCancelled()) {
                Instruction instruction = iterator.next();
                instructionCount++;
                instructions.write(tsv(
                    focus.label, rva(function.getEntryPoint().getOffset()),
                    rva(instruction.getAddress().getOffset()),
                    bytes(instruction), instruction.getMnemonicString(),
                    instruction, instruction.getFlowType()));

                for (Reference reference : instruction.getReferencesFrom()) {
                    Function target =
                        getFunctionContaining(reference.getToAddress());
                    references.write(tsv(
                        focus.label,
                        rva(function.getEntryPoint().getOffset()),
                        rva(instruction.getAddress().getOffset()),
                        reference.getReferenceType(), reference.getToAddress(),
                        rva(reference.getToAddress().getOffset()),
                        target == null ? "" : target.getName(),
                        target == null
                            ? ""
                            : rva(target.getEntryPoint().getOffset())));
                }

                for (int operandIndex = 0;
                     operandIndex < instruction.getNumOperands();
                     operandIndex++) {
                    for (Object object :
                         instruction.getOpObjects(operandIndex)) {
                        if (object instanceof Scalar) {
                            Scalar scalar = (Scalar)object;
                            scalars.write(tsv(
                                focus.label,
                                rva(function.getEntryPoint().getOffset()),
                                rva(instruction.getAddress().getOffset()),
                                instruction.getMnemonicString(), operandIndex,
                                String.format(
                                    "0x%x", scalar.getUnsignedValue()),
                                instruction
                                    .getDefaultOperandRepresentation(
                                        operandIndex)));
                        }
                    }
                }
            }

            functions.write(tsv(
                focus.label, rva(focus.address),
                rva(function.getEntryPoint().getOffset()),
                function.getName(), function.getBody().getNumAddresses(),
                instructionCount, function.getCallingConventionName(),
                bytes(function.getEntryPoint(), 16)));
        }

        functions.close();
        instructions.close();
        references.close();
        scalars.close();
    }

    private void exportFocusMemory() throws Exception {
        BufferedWriter out = writer("focus_memory.tsv");
        out.write("label\trva\tbytes\n");
        out.write(tsv(
            "unoccupied_nearest_radius", rva(0x100e5908L),
            bytes(toAddr(0x100e5908L), 4)));
        out.write(tsv(
            "camera_matrix_pointer_literal", rva(0x1009ffaeL),
            bytes(toAddr(0x1009ffaeL), 8)));
        out.close();
    }

    private BufferedWriter writer(String name) throws Exception {
        return new BufferedWriter(new FileWriter(new File(outDir, name)));
    }

    private String bytes(Instruction instruction) throws Exception {
        return hex(instruction.getBytes());
    }

    private String bytes(Address address, int count) throws Exception {
        byte[] values = new byte[count];
        currentProgram.getMemory().getBytes(address, values);
        return hex(values);
    }

    private String hex(byte[] values) {
        StringBuilder out = new StringBuilder(values.length * 2);
        for (byte value : values) {
            out.append(String.format("%02x", value & 0xff));
        }
        return out.toString();
    }

    private String tsv(Object... columns) {
        StringBuilder out = new StringBuilder();
        for (int index = 0; index < columns.length; index++) {
            if (index > 0) {
                out.append('\t');
            }
            out.append(String.valueOf(columns[index])
                .replace("\t", " ")
                .replace("\n", "\\n"));
        }
        out.append('\n');
        return out.toString();
    }

    private String rva(long address) {
        if (address < IMAGE_BASE || address >= 0x20000000L) {
            return String.format("external:0x%08x", address);
        }
        return String.format("0x%08x", address - IMAGE_BASE);
    }
}
