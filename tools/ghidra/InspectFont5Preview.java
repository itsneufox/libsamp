// STATIC_037 focused metadata export for the SA-MP 0.3.7-R5 Font 5 path.
// Emits compact call/data/constant metadata only; no decompiler pseudocode.

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

public class InspectFont5Preview extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;
    private static final long[] FOCUS_FUNCTIONS = new long[] {
        0x100b3480L, // cached-preview versus normal CFont dispatch
        0x100b34a0L  // style-5 preview preparation/cache
    };

    private File outDir;

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException("usage: InspectFont5Preview.java <output-dir>");
        }
        outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());
        exportFocusMetadata();
    }

    private void exportFocusMetadata() throws Exception {
        BufferedWriter functions = writer("font5_functions.tsv");
        BufferedWriter calls = writer("font5_calls.tsv");
        BufferedWriter data = writer("font5_data_refs.tsv");
        BufferedWriter constants = writer("font5_constants.tsv");
        BufferedWriter incoming = writer("font5_incoming.tsv");

        functions.write("function\tfunction_rva\tsize\tcall_in\tcall_out\tdata_refs_from\tcalling_convention\n");
        calls.write("function_rva\tcallsite_rva\tmnemonic\toperand\ttarget\ttarget_rva\tref_type\n");
        data.write("function_rva\tinsn_rva\tmnemonic\toperand\ttarget\ttarget_rva\tref_type\n");
        constants.write("function_rva\tinsn_rva\tmnemonic\toperand_index\tvalue\toperand\n");
        incoming.write("function_rva\tfrom_function\tfrom_function_rva\tfrom_rva\tref_type\n");

        for (long addressValue : FOCUS_FUNCTIONS) {
            Function function = getFunctionContaining(toAddr(addressValue));
            if (function == null) {
                functions.write(tsv("missing", rva(addressValue), 0, 0, 0, 0, ""));
                continue;
            }

            int callIn = 0;
            int callOut = 0;
            int dataRefs = 0;
            ReferenceIterator incomingRefs = currentProgram.getReferenceManager().getReferencesTo(function.getEntryPoint());
            while (incomingRefs.hasNext() && !monitor.isCancelled()) {
                Reference ref = incomingRefs.next();
                if (!ref.getReferenceType().isCall()) {
                    continue;
                }
                Function from = getFunctionContaining(ref.getFromAddress());
                incoming.write(tsv(rva(function.getEntryPoint().getOffset()), from == null ? "" : from.getName(),
                    from == null ? "" : rva(from.getEntryPoint().getOffset()), rva(ref.getFromAddress().getOffset()),
                    ref.getReferenceType()));
                callIn++;
            }

            InstructionIterator instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
            while (instructions.hasNext() && !monitor.isCancelled()) {
                Instruction instruction = instructions.next();
                boolean callInstruction = instruction.getFlowType().isCall();
                boolean emittedCallReference = false;
                for (Reference ref : instruction.getReferencesFrom()) {
                    Function target = getFunctionContaining(ref.getToAddress());
                    if (ref.getReferenceType().isCall()) {
                        calls.write(tsv(rva(function.getEntryPoint().getOffset()), rva(instruction.getAddress().getOffset()),
                            instruction.getMnemonicString(), instruction.toString(),
                            target == null ? ref.getToAddress() : target.getName(), rva(ref.getToAddress().getOffset()),
                            ref.getReferenceType()));
                        callOut++;
                        emittedCallReference = true;
                    } else if (ref.getReferenceType().isData()) {
                        data.write(tsv(rva(function.getEntryPoint().getOffset()), rva(instruction.getAddress().getOffset()),
                            instruction.getMnemonicString(), instruction.toString(), ref.getToAddress(),
                            rva(ref.getToAddress().getOffset()), ref.getReferenceType()));
                        dataRefs++;
                    }
                }
                if (callInstruction && !emittedCallReference) {
                    calls.write(tsv(rva(function.getEntryPoint().getOffset()), rva(instruction.getAddress().getOffset()),
                        instruction.getMnemonicString(), instruction.toString(), "indirect", "", "INDIRECT"));
                    callOut++;
                }
                for (int operandIndex = 0; operandIndex < instruction.getNumOperands(); operandIndex++) {
                    for (Object object : instruction.getOpObjects(operandIndex)) {
                        if (object instanceof Scalar) {
                            long value = ((Scalar)object).getUnsignedValue();
                            constants.write(tsv(rva(function.getEntryPoint().getOffset()),
                                rva(instruction.getAddress().getOffset()), instruction.getMnemonicString(), operandIndex,
                                String.format("0x%x", value), instruction.getDefaultOperandRepresentation(operandIndex)));
                        }
                    }
                }
            }
            functions.write(tsv(function.getName(), rva(function.getEntryPoint().getOffset()),
                function.getBody().getNumAddresses(), callIn, callOut, dataRefs, function.getCallingConventionName()));
        }

        functions.close();
        calls.close();
        data.close();
        constants.close();
        incoming.close();
    }

    private BufferedWriter writer(String name) throws Exception {
        return new BufferedWriter(new FileWriter(new File(outDir, name)));
    }

    private String tsv(Object... columns) {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < columns.length; index++) {
            if (index > 0) {
                result.append('\t');
            }
            result.append(String.valueOf(columns[index]).replace("\t", " ").replace("\n", "\\n"));
        }
        result.append('\n');
        return result.toString();
    }

    private String rva(long address) {
        return String.format("0x%08x", address - IMAGE_BASE);
    }
}
