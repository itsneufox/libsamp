// STATIC_037 bounded instruction export for the eight inbound handlers that
// were absent from the replacement RPC inventory on 2026-07-26.  The report
// intentionally contains instructions and call targets, not decompiler output.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;

public class InspectLegacyRpcGapHandlers extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;
    private static final long[] HANDLER_RVAS = {
        0x1dcc0L, 0x18c50L, 0x18b70L, 0x18ac0L,
        0x180c0L, 0x18d00L, 0x17de0L, 0x1c170L
    };
    private static final int[] RPC_IDS = {
        48, 92, 98, 111, 125, 150, 167, 169
    };

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: InspectLegacyRpcGapHandlers.java <output-dir>");
        }

        File outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());
        try (BufferedWriter identity =
                 new BufferedWriter(new FileWriter(new File(outDir, "identity.tsv")));
             BufferedWriter functions =
                 new BufferedWriter(new FileWriter(new File(outDir, "functions.tsv")));
             BufferedWriter instructions =
                 new BufferedWriter(new FileWriter(new File(outDir, "instructions.tsv")))) {
            identity.write("property\tvalue\n");
            identity.write("sha256\t" + currentProgram.getExecutableSHA256() + "\n");
            identity.write("image_base\t" + currentProgram.getImageBase() + "\n");
            identity.write("language\t" + currentProgram.getLanguageID() + "\n");
            functions.write("rpc_id\thandler_rva\tfunction_end_rva\tinstruction_count\n");
            instructions.write(
                "rpc_id\thandler_rva\tinsn_rva\tbytes\tmnemonic\toperand0\toperand1\n");

            for (int index = 0; index < HANDLER_RVAS.length; ++index) {
                long entry = IMAGE_BASE + HANDLER_RVAS[index];
                Function function = getFunctionContaining(toAddr(entry));
                if (function != null && function.getEntryPoint().getOffset() != entry) {
                    throw new IllegalStateException(
                        "handler entry is inside another function for RPC " + RPC_IDS[index]);
                }

                int count = 0;
                long functionEnd = entry;
                if (function == null) {
                    // RPC 125 is a one-byte RET and is not always promoted to a
                    // function by a clean auto-analysis. Preserve that exact
                    // registered entry instruction in the bounded report.
                    Instruction instruction =
                        currentProgram.getListing().getInstructionAt(toAddr(entry));
                    if (instruction == null) {
                        disassemble(toAddr(entry));
                        instruction =
                            currentProgram.getListing().getInstructionAt(toAddr(entry));
                    }
                    if (instruction == null) {
                        throw new IllegalStateException(
                            "handler instruction not found for RPC " + RPC_IDS[index]);
                    }
                    writeInstruction(instructions, RPC_IDS[index], entry, instruction);
                    functionEnd = entry + instruction.getLength() - 1;
                    count = 1;
                } else {
                    functionEnd = function.getBody().getMaxAddress().getOffset();
                    InstructionIterator iterator =
                        currentProgram.getListing().getInstructions(function.getBody(), true);
                    while (iterator.hasNext() && !monitor.isCancelled()) {
                        Instruction instruction = iterator.next();
                        writeInstruction(instructions, RPC_IDS[index], entry, instruction);
                        count++;
                    }
                }
                functions.write(RPC_IDS[index] + "\t" + rva(entry) + "\t" +
                    rva(functionEnd) + "\t" + count + "\n");
            }
        }
    }

    private void writeInstruction(
            BufferedWriter instructions, int rpcId, long entry,
            Instruction instruction) throws Exception {
        instructions.write(rpcId + "\t" +
            rva(entry) + "\t" +
            rva(instruction.getAddress().getOffset()) + "\t" +
            bytes(instruction) + "\t" +
            instruction.getMnemonicString() + "\t" +
            operand(instruction, 0) + "\t" +
            operand(instruction, 1) + "\n");
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
