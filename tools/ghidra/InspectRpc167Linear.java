// STATIC_037 bounded linear instruction export for the registered RPC 167
// handler whose default Ghidra function body stops after the first PUSH.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Instruction;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;

public class InspectRpc167Linear extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;
    private static final long ENTRY_RVA = 0x17de0L;

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: InspectRpc167Linear.java <output-dir>");
        }

        File outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());
        try (BufferedWriter out = new BufferedWriter(
                 new FileWriter(new File(outDir, "rpc167_linear.tsv")))) {
            out.write("property\tvalue\n");
            out.write("sha256\t" + currentProgram.getExecutableSHA256() + "\n");
            out.write("handler_rva\t0x00017de0\n");
            out.write("insn_rva\tbytes\tmnemonic\toperand0\toperand1\n");

            long address = IMAGE_BASE + ENTRY_RVA;
            boolean sawRet = false;
            for (int count = 0; count < 128 && !monitor.isCancelled(); ++count) {
                Instruction instruction =
                    currentProgram.getListing().getInstructionAt(toAddr(address));
                if (instruction == null) {
                    disassemble(toAddr(address));
                    instruction =
                        currentProgram.getListing().getInstructionAt(toAddr(address));
                }
                if (instruction == null) {
                    throw new IllegalStateException(
                        "instruction not found at " + rva(address));
                }
                out.write(rva(address) + "\t" + bytes(instruction) + "\t" +
                    instruction.getMnemonicString() + "\t" +
                    operand(instruction, 0) + "\t" +
                    operand(instruction, 1) + "\n");
                address += instruction.getLength();
                if ("RET".equals(instruction.getMnemonicString())) {
                    sawRet = true;
                    break;
                }
            }
            if (!sawRet) {
                throw new IllegalStateException(
                    "RPC 167 linear scan did not reach RET within 128 instructions");
            }
        }
    }

    private String operand(Instruction instruction, int index) {
        if (index >= instruction.getNumOperands()) {
            return "";
        }
        return instruction.getDefaultOperandRepresentation(index)
            .replace('\t', ' ').replace('\n', ' ');
    }

    private String bytes(Instruction instruction) throws Exception {
        byte[] data = new byte[instruction.getLength()];
        currentProgram.getMemory().getBytes(instruction.getAddress(), data);
        StringBuilder out = new StringBuilder();
        for (int index = 0; index < data.length; ++index) {
            if (index != 0) {
                out.append(' ');
            }
            out.append(String.format("%02x", data[index] & 0xff));
        }
        return out.toString();
    }

    private String rva(long address) {
        return String.format("0x%08x", address - IMAGE_BASE);
    }
}
