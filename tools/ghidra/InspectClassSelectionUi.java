// STATIC_037 focused metadata export for the SA-MP 0.3.7-R5 class-selection UI.
// Emits bounded instruction/reference/scalar metadata only; no decompiler
// pseudocode and no proprietary resource data.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;

public class InspectClassSelectionUi extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;

    private static final Window[] WINDOWS = new Window[] {
        new Window("class_dialog_setup", 0x100c58a8L, 0x100c5977L),
        new Window("class_dialog_activate_and_place", 0x10006150L, 0x100061a4L),
        new Window("dxut_default_font_and_button_skin", 0x1008d780L, 0x1008d91eL),
        new Window("ui_font_settings_helpers", 0x100c5320L, 0x100c539fL)
    };

    private File outDir;

    private static class Window {
        final String label;
        final long first;
        final long lastExclusive;

        Window(String label, long first, long lastExclusive) {
            this.label = label;
            this.first = first;
            this.lastExclusive = lastExclusive;
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException(
                "usage: InspectClassSelectionUi.java <output-dir>");
        }
        outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());
        exportIdentity();
        exportInstructions();
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

    private void exportInstructions() throws Exception {
        BufferedWriter out = writer("instructions.tsv");
        out.write(
            "label\tinsn_rva\tbytes\tmnemonic\tinstruction\treferences"
                + "\tscalars\n");

        for (Window window : WINDOWS) {
            Address cursor = toAddr(window.first);
            Address end = toAddr(window.lastExclusive);
            while (cursor.compareTo(end) < 0 && !monitor.isCancelled()) {
                Instruction instruction =
                    currentProgram.getListing().getInstructionAt(cursor);
                if (instruction == null) {
                    cursor = cursor.add(1);
                    continue;
                }

                StringBuilder references = new StringBuilder();
                for (Reference reference : instruction.getReferencesFrom()) {
                    if (references.length() != 0) {
                        references.append(',');
                    }
                    references.append(reference.getReferenceType())
                        .append(':')
                        .append(rva(reference.getToAddress().getOffset()));
                }

                StringBuilder scalars = new StringBuilder();
                for (int operandIndex = 0;
                     operandIndex < instruction.getNumOperands();
                     operandIndex++) {
                    for (Object object :
                         instruction.getOpObjects(operandIndex)) {
                        if (object instanceof Scalar) {
                            if (scalars.length() != 0) {
                                scalars.append(',');
                            }
                            scalars.append(operandIndex)
                                .append(':')
                                .append(String.format(
                                    "0x%x",
                                    ((Scalar)object).getUnsignedValue()));
                        }
                    }
                }

                out.write(tsv(
                    window.label, rva(instruction.getAddress().getOffset()),
                    hex(instruction.getBytes()),
                    instruction.getMnemonicString(), instruction,
                    references, scalars));
                cursor = instruction.getMaxAddress().add(1);
            }
        }
        out.close();
    }

    private BufferedWriter writer(String name) throws Exception {
        return new BufferedWriter(new FileWriter(new File(outDir, name)));
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
