// STATIC_037 bounded instruction export for the R5 vehicle-wrapper method
// called by inbound RPC 98 after its uint16 vehicle-id and uint8 status read.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;

public class InspectVehicleTireStatus extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;
    private static final long ENTRY_RVA = 0xb7940L;

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: InspectVehicleTireStatus.java <output-dir>");
        }

        File outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());
        try (BufferedWriter out = new BufferedWriter(
                 new FileWriter(new File(outDir, "rpc98_tire_method.tsv")))) {
            long entry = IMAGE_BASE + ENTRY_RVA;
            Function function = getFunctionAt(toAddr(entry));
            if (function == null) {
                throw new IllegalStateException(
                    "RPC 98 tire method function missing at 0x000b7940");
            }

            out.write("property\tvalue\n");
            out.write("sha256\t" + currentProgram.getExecutableSHA256() + "\n");
            out.write("entry_rva\t0x000b7940\n");
            out.write("end_rva\t" +
                rva(function.getBody().getMaxAddress().getOffset()) + "\n");
            out.write("insn_rva\tbytes\tmnemonic\toperand0\toperand1\n");

            InstructionIterator iterator =
                currentProgram.getListing().getInstructions(function.getBody(), true);
            int count = 0;
            while (iterator.hasNext() && !monitor.isCancelled()) {
                if (++count > 256) {
                    throw new IllegalStateException(
                        "RPC 98 tire method exceeded 256-instruction bound");
                }
                Instruction instruction = iterator.next();
                out.write(rva(instruction.getAddress().getOffset()) + "\t" +
                    bytes(instruction) + "\t" +
                    instruction.getMnemonicString() + "\t" +
                    operand(instruction, 0) + "\t" +
                    operand(instruction, 1) + "\n");
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
