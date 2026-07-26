// STATIC_037 focused export for the SA-MP 0.3.7-R5 inbound RPC
// registration block.  It records bounded instruction metadata and the
// handler/ID pairs passed to RakNet; it emits no decompiler pseudocode.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;

public class InspectRpcRegistration60 extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;
    private static final long REGISTRATION_ENTRY = 0x1001e130L;

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: InspectRpcRegistration60.java <output-dir>");
        }

        File outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());

        Function function = getFunctionContaining(toAddr(REGISTRATION_ENTRY));
        if (function == null ||
            function.getEntryPoint().getOffset() != REGISTRATION_ENTRY) {
            throw new IllegalStateException("registration function not found");
        }

        try (BufferedWriter identity =
                 new BufferedWriter(new FileWriter(new File(outDir, "identity.tsv")));
             BufferedWriter instructions =
                 new BufferedWriter(new FileWriter(new File(outDir, "instructions.tsv")));
             BufferedWriter pairs =
                 new BufferedWriter(new FileWriter(new File(outDir, "registration_pairs.tsv")));
             BufferedWriter summary =
                 new BufferedWriter(new FileWriter(new File(outDir, "summary.tsv")))) {
            identity.write("property\tvalue\n");
            identity.write("sha256\t" + currentProgram.getExecutableSHA256() + "\n");
            identity.write("image_base\t" + currentProgram.getImageBase() + "\n");
            identity.write("language\t" + currentProgram.getLanguageID() + "\n");

            instructions.write("insn_rva\tbytes\tmnemonic\toperand0\toperand1\n");
            pairs.write("callsite_rva\tid_storage_rva\trpc_id\thandler_rva\n");

            int pairCount = 0;
            int id60Count = 0;
            Instruction previous = null;
            InstructionIterator iterator =
                currentProgram.getListing().getInstructions(function.getBody(), true);
            while (iterator.hasNext() && !monitor.isCancelled()) {
                Instruction instruction = iterator.next();
                instructions.write(rva(instruction.getAddress().getOffset()) + "\t" +
                    bytes(instruction) + "\t" + instruction.getMnemonicString() + "\t" +
                    operand(instruction, 0) + "\t" + operand(instruction, 1) + "\n");

                if (previous != null &&
                    "PUSH".equals(previous.getMnemonicString()) &&
                    "PUSH".equals(instruction.getMnemonicString())) {
                    Long handler = immediate(previous);
                    Long idStorage = immediate(instruction);
                    if (handler != null && idStorage != null &&
                        handler >= IMAGE_BASE && handler < IMAGE_BASE + 0x1000000L &&
                        idStorage >= IMAGE_BASE && idStorage < IMAGE_BASE + 0x1000000L) {
                        int rpcId = getInt(toAddr(idStorage)) & 0xff;
                        pairs.write(rva(instruction.getAddress().getOffset()) + "\t" +
                            rva(idStorage) + "\t" + rpcId + "\t" + rva(handler) + "\n");
                        pairCount++;
                        if (rpcId == 60) {
                            id60Count++;
                        }
                    }
                }
                previous = instruction;
            }

            summary.write("property\tvalue\n");
            summary.write("registration_function_rva\t" +
                rva(function.getEntryPoint().getOffset()) + "\n");
            summary.write("registration_function_end_rva\t" +
                rva(function.getBody().getMaxAddress().getOffset()) + "\n");
            summary.write("registration_pair_count\t" + pairCount + "\n");
            summary.write("rpc60_pair_count\t" + id60Count + "\n");
        }
    }

    private Long immediate(Instruction instruction) {
        for (Object object : instruction.getOpObjects(0)) {
            if (object instanceof Address) {
                return ((Address)object).getOffset();
            }
            if (object instanceof Scalar) {
                return ((Scalar)object).getUnsignedValue();
            }
        }
        return null;
    }

    private String operand(Instruction instruction, int index) {
        if (index >= instruction.getNumOperands()) {
            return "";
        }
        return instruction.getDefaultOperandRepresentation(index)
            .replace('\t', ' ').replace('\n', ' ');
    }

    private String bytes(Instruction instruction) throws Exception {
        return bytes(instruction.getAddress(), instruction.getLength());
    }

    private String bytes(Address address, int count) throws Exception {
        byte[] data = new byte[count];
        currentProgram.getMemory().getBytes(address, data);
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < data.length; ++i) {
            if (i != 0) {
                out.append(' ');
            }
            out.append(String.format("%02x", data[i] & 0xff));
        }
        return out.toString();
    }

    private String rva(long address) {
        return String.format("0x%08x", address - IMAGE_BASE);
    }
}
