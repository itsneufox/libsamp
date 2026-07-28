// STATIC_037 focused metadata export for the SA-MP 0.3.7-R5 custom
// ModelInfo implementation.  The output is deliberately limited to
// instructions, references, constants, patch records, and bounded memory
// metadata; it does not emit decompiler pseudocode.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.nio.file.Files;

public class InspectCustomModelInfo extends GhidraScript {
    private static final long SAMP_IMAGE_BASE = 0x10000000L;

    private static final long MODEL_POINTER_PATCH_TABLE_US1 = 0x10114b10L;
    private static final long MODEL_POINTER_PATCH_TABLE_VARIANT2 = 0x101158e0L;
    private static final int MODEL_POINTER_PATCH_COUNT = 707;
    private static final int MODEL_POINTER_PATCH_RECORD_SIZE = 5;

    private static final long ATOMIC_STORE_PATCH_TABLE = 0x10116720L;
    private static final int ATOMIC_STORE_PATCH_COUNT = 14;
    private static final long VANILLA_MODEL_POINTER_BASE = 0x00a9b0c8L;
    private static final long VANILLA_ATOMIC_STORE_BASE = 0x00aae954L;
    private static final long RELOCATED_MODEL_POINTER_STORAGE = 0x101625b0L;
    private static final long RELOCATED_MODEL_POINTER_ORIGIN = 0x101825acL;
    private static final long RELOCATED_ATOMIC_STORE = 0x101cebd8L;

    private static final RawSpan[] SAMP_RAW_SPANS = new RawSpan[] {
        new RawSpan("custom_model_release_tick", 0x1000d1e0L, 0x55),
        new RawSpan(
            "negative_model_id_guard_trampoline", 0x100a5e90L, 0x15),
        new RawSpan("free_cloned_model_info", 0x100a7b30L, 0x29),
        new RawSpan("bootstrap_calls_pregame_patch_entry", 0x100c3a80L, 0x50)
    };

    private static final FixedGuard[] GTA_FIXED_GUARDS =
        new FixedGuard[] {
            new FixedGuard(
                "negative_model_id_guard_hook", 0x004087eaL,
                "56578d7cad00"),
            new FixedGuard(
                "ped_model_info_store_operand", 0x004c67adL,
                "fc78b400"),
            new FixedGuard(
                "txd_store_capacity_operand", 0x00731f60L,
                "88130000")
        };

    private static final Focus[] SAMP_FOCUS = new Focus[] {
        new Focus("custom_model_manager_init", 0x1000bd60L),
        new Focus("custom_download_ped_loader", 0x1000c650L),
        new Focus("custom_download_atomic_loader", 0x1000c770L),
        new Focus("custom_model_release_tick", 0x1000d1e0L),
        new Focus("negative_model_id_guard_trampoline", 0x100a5e90L),
        new Focus("negative_model_id_guard_installer", 0x100a6ff0L),
        new Focus("install_model_pointer_patches", 0x100a7970L),
        new Focus("initialize_model_pointer_arena", 0x100a7a00L),
        new Focus("get_model_info_compat", 0x100a7a40L),
        new Focus("clone_ped_model_info", 0x100a7a80L),
        new Focus("clone_atomic_model_info", 0x100a7ad0L),
        new Focus("free_cloned_model_info", 0x100a7b30L),
        new Focus("load_or_bind_txd", 0x100a7b60L),
        new Focus("load_custom_ped_model", 0x100a7bd0L),
        new Focus("load_custom_atomic_model", 0x100a7c30L),
        new Focus("load_custom_collision", 0x100a7cc0L),
        new Focus("register_custom_collision_handler", 0x100a7d90L),
        new Focus("pregame_patch_entry", 0x100a08e0L),
        new Focus("pregame_limit_patch_group", 0x100aa590L),
        new Focus("initialize_ped_model_store_319", 0x100aa9c0L),
        new Focus("initialize_atomic_model_store_20000", 0x100aaa10L),
        new Focus("initialize_world_sector_store_not_modelinfo", 0x100aaa80L),
        new Focus("install_pregame_patch_set", 0x100aaeb0L),
        new Focus("bootstrap_calls_pregame_patch_entry", 0x100c3a80L),
        new Focus("txd_find_slot_wrapper", 0x100b3880L),
        new Focus("txd_add_slot_wrapper", 0x100b38a0L),
        new Focus("txd_load_wrapper", 0x100b38c0L),
        new Focus("txd_add_ref_wrapper", 0x100b38f0L),
        new Focus("txd_remove_ref_wrapper", 0x100b3900L),
        new Focus("txd_push_current_wrapper", 0x100b3910L),
        new Focus("txd_pop_current_wrapper", 0x100b3920L),
        new Focus("txd_set_current_wrapper", 0x100b3930L),
        new Focus("txd_remove_named_slot_wrapper", 0x100b3980L),
        new Focus("txd_load_slot_wrapper", 0x100b39b0L),
        new Focus("txd_remove_slot_wrapper", 0x100b39d0L),
        new Focus("txd_get_wrapper", 0x100b39f0L),
        new Focus("validate_ped_clone_source", 0x100b3dd0L),
        new Focus("validate_atomic_clone_source", 0x100b44e0L),
        new Focus("set_model_txd_index", 0x100b4660L),
        new Focus("get_model_txd_index", 0x100b4680L),
        new Focus("release_model_txd_if_unreferenced", 0x100b2040L)
    };

    private static final Region[] SAMP_REGIONS = new Region[] {
        new Region(
            "model_pointer_patch_table_us1", MODEL_POINTER_PATCH_TABLE_US1,
            MODEL_POINTER_PATCH_COUNT * MODEL_POINTER_PATCH_RECORD_SIZE, 5,
            MODEL_POINTER_PATCH_COUNT),
        new Region(
            "model_pointer_patch_table_variant2",
            MODEL_POINTER_PATCH_TABLE_VARIANT2,
            MODEL_POINTER_PATCH_COUNT * MODEL_POINTER_PATCH_RECORD_SIZE, 5,
            MODEL_POINTER_PATCH_COUNT),
        new Region(
            "atomic_store_patch_table", ATOMIC_STORE_PATCH_TABLE,
            ATOMIC_STORE_PATCH_COUNT * 4L, 4, ATOMIC_STORE_PATCH_COUNT),
        new Region(
            "model_pointer_storage", RELOCATED_MODEL_POINTER_STORAGE,
            65535L * 4L, 4, 65535),
        new Region(
            "model_pointer_effective_origin", RELOCATED_MODEL_POINTER_ORIGIN,
            4, 4, 1),
        new Region(
            "atomic_model_info_store", RELOCATED_ATOMIC_STORE,
            20000L * 0x20L, 0x20, 20000),
        new Region(
            "ped_model_info_store", 0x101c9718L, 319L * 0x44L, 0x44, 319),
        new Region(
            "world_sector_store_not_modelinfo", 0x101a2618L,
            20000L * 8L, 8, 20000)
    };

    private static final StringAnchor[] STRING_ANCHORS =
        new StringAnchor[] {
            new StringAnchor("download_model_path_dff", 0x100e5bd8L),
            new StringAnchor("download_model_path_txd", 0x100e5be8L),
            new StringAnchor("download_txd_warning", 0x100e5c30L),
            new StringAnchor("download_dff_path", 0x100e5ca8L),
            new StringAnchor("download_txd_path", 0x100e5cb4L),
            new StringAnchor("loader_failed_texture", 0x100ecc1cL),
            new StringAnchor("loader_failed_model", 0x100ecc4cL),
            new StringAnchor("loader_failed_collision_alloc", 0x100ecc70L),
            new StringAnchor("loader_failed_collision_load", 0x100ecca4L),
            new StringAnchor("loader_not_col3", 0x100eccd0L),
            new StringAnchor("fallback_txd_name", 0x100ed3e4L),
            new StringAnchor("samp_asset_directory", 0x100ed3eaL)
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

    private static class RawSpan {
        final String label;
        final long address;
        final int size;

        RawSpan(String label, long address, int size) {
            this.label = label;
            this.address = address;
            this.size = size;
        }
    }

    private static class FixedGuard {
        final String label;
        final long address;
        final String expectedBytes;

        FixedGuard(String label, long address, String expectedBytes) {
            this.label = label;
            this.address = address;
            this.expectedBytes = expectedBytes;
        }
    }

    private static class Region {
        final String label;
        final long start;
        final long size;
        final long stride;
        final long count;

        Region(String label, long start, long size, long stride, long count) {
            this.label = label;
            this.start = start;
            this.size = size;
            this.stride = stride;
            this.count = count;
        }
    }

    private static class StringAnchor {
        final String label;
        final long address;

        StringAnchor(String label, long address) {
            this.label = label;
            this.address = address;
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException(
                "usage: InspectCustomModelInfo.java "
                    + "<export-samp|verify-gta> <output-dir> [patch-table.tsv]");
        }

        outDir = new File(args[1]);
        Files.createDirectories(outDir.toPath());
        exportIdentity();

        if ("export-samp".equals(args[0])) {
            exportSampMetadata();
            exportPatchTables();
            exportRegions();
            exportStrings();
            exportRawSpans();
            return;
        }
        if ("verify-gta".equals(args[0])) {
            if (args.length < 3) {
                throw new IllegalArgumentException(
                    "verify-gta requires patch-table.tsv");
            }
            verifyGtaPatchGuards(new File(args[2]));
            return;
        }
        throw new IllegalArgumentException("unknown mode: " + args[0]);
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

    private void exportSampMetadata() throws Exception {
        BufferedWriter functions = writer("functions.tsv");
        BufferedWriter instructions = writer("instructions.tsv");
        BufferedWriter references = writer("references.tsv");
        BufferedWriter callers = writer("callers.tsv");
        BufferedWriter scalars = writer("scalars.tsv");

        functions.write(
            "label\trequested_rva\tentry_rva\tname\tsize\tinstruction_count"
                + "\tcalling_convention\tentry_bytes_16"
                + "\tdirect_reference_count\n");
        instructions.write(
            "label\tfunction_rva\tinsn_rva\tbytes\tmnemonic\tinstruction"
                + "\tflow_type\n");
        references.write(
            "label\tfunction_rva\tinsn_rva\tref_type\ttarget\ttarget_rva"
                + "\ttarget_function\ttarget_function_rva\n");
        callers.write(
            "label\tfunction_rva\tcaller_rva\tref_type\tcaller_function"
                + "\tcaller_function_rva\n");
        scalars.write(
            "label\tfunction_rva\tinsn_rva\tmnemonic\toperand_index\tvalue"
                + "\toperand\n");

        for (Focus focus : SAMP_FOCUS) {
            Function function = getFunctionContaining(toAddr(focus.address));
            Address referenceTarget =
                function == null
                    ? toAddr(focus.address)
                    : function.getEntryPoint();
            int directReferenceCount = 0;
            ReferenceIterator referenceIterator =
                currentProgram.getReferenceManager().getReferencesTo(
                    referenceTarget);
            while (referenceIterator.hasNext()) {
                Reference reference = referenceIterator.next();
                Function caller =
                    getFunctionContaining(reference.getFromAddress());
                callers.write(tsv(
                    focus.label, sampRva(referenceTarget.getOffset()),
                    sampRva(reference.getFromAddress().getOffset()),
                    reference.getReferenceType(),
                    caller == null ? "" : caller.getName(),
                    caller == null
                        ? ""
                        : sampRva(caller.getEntryPoint().getOffset())));
                directReferenceCount++;
            }

            if (function == null) {
                functions.write(tsv(
                    focus.label, sampRva(focus.address), "", "missing", 0, 0,
                    "", "", directReferenceCount));
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
                    focus.label,
                    sampRva(function.getEntryPoint().getOffset()),
                    sampRva(instruction.getAddress().getOffset()),
                    bytes(instruction), instruction.getMnemonicString(),
                    instruction, instruction.getFlowType()));

                for (Reference reference : instruction.getReferencesFrom()) {
                    Function target =
                        getFunctionContaining(reference.getToAddress());
                    references.write(tsv(
                        focus.label,
                        sampRva(function.getEntryPoint().getOffset()),
                        sampRva(instruction.getAddress().getOffset()),
                        reference.getReferenceType(), reference.getToAddress(),
                        sampRva(reference.getToAddress().getOffset()),
                        target == null ? "" : target.getName(),
                        target == null
                            ? ""
                            : sampRva(target.getEntryPoint().getOffset())));
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
                                sampRva(function.getEntryPoint().getOffset()),
                                sampRva(instruction.getAddress().getOffset()),
                                instruction.getMnemonicString(), operandIndex,
                                String.format(
                                    "0x%x", scalar.getUnsignedValue()),
                                instruction.getDefaultOperandRepresentation(
                                    operandIndex)));
                        }
                    }
                }
            }

            functions.write(tsv(
                focus.label, sampRva(focus.address),
                sampRva(function.getEntryPoint().getOffset()),
                function.getName(), function.getBody().getNumAddresses(),
                instructionCount, function.getCallingConventionName(),
                bytes(function.getEntryPoint(), 16), directReferenceCount));
        }

        functions.close();
        instructions.close();
        references.close();
        callers.close();
        scalars.close();
    }

    private void exportPatchTables() throws Exception {
        BufferedWriter out = writer("patch_tables.tsv");
        out.write(
            "table\tindex\ttable_rva\ttarget_va\texpected_opcode"
                + "\toperand_offset\toriginal_value\tpatched_value"
                + "\tpatch_width\n");
        exportModelPointerPatchTable(
            out, "model_pointer_us1", MODEL_POINTER_PATCH_TABLE_US1);
        exportModelPointerPatchTable(
            out, "model_pointer_variant2",
            MODEL_POINTER_PATCH_TABLE_VARIANT2);

        for (int index = 0; index < ATOMIC_STORE_PATCH_COUNT; index++) {
            Address record =
                toAddr(ATOMIC_STORE_PATCH_TABLE + index * 4L);
            long target = unsignedInt(record);
            out.write(tsv(
                "atomic_store_us1", index,
                sampRva(record.getOffset()), va(target), "", 0,
                va(VANILLA_ATOMIC_STORE_BASE),
                sampRva(RELOCATED_ATOMIC_STORE), 4));
        }
        out.close();
    }

    private void exportModelPointerPatchTable(
            BufferedWriter out, String label, long tableAddress)
            throws Exception {
        for (int index = 0; index < MODEL_POINTER_PATCH_COUNT; index++) {
            Address record =
                toAddr(
                    tableAddress
                        + index * (long)MODEL_POINTER_PATCH_RECORD_SIZE);
            long target = unsignedInt(record);
            int opcode =
                currentProgram.getMemory().getByte(record.add(4)) & 0xff;
            int operandOffset = operandOffsetForOpcode(opcode);
            out.write(tsv(
                label, index, sampRva(record.getOffset()), va(target),
                String.format("%02x", opcode), operandOffset,
                va(VANILLA_MODEL_POINTER_BASE),
                sampRva(RELOCATED_MODEL_POINTER_ORIGIN), 4));
        }
    }

    private void exportRegions() throws Exception {
        BufferedWriter out = writer("regions.tsv");
        out.write(
            "label\tstart_rva\tend_exclusive_rva\tsize\tstride\tcount"
                + "\tmemory_block\tinitialized\tread\twrite\texecute\n");
        for (Region region : SAMP_REGIONS) {
            Address start = toAddr(region.start);
            MemoryBlock block =
                currentProgram.getMemory().getBlock(start);
            out.write(tsv(
                region.label, sampRva(region.start),
                sampRva(region.start + region.size), hex(region.size),
                hex(region.stride), region.count,
                block == null ? "" : block.getName(),
                block != null && block.isInitialized(),
                block != null && block.isRead(),
                block != null && block.isWrite(),
                block != null && block.isExecute()));
        }
        out.close();

        BufferedWriter blocks = writer("memory_blocks.tsv");
        blocks.write(
            "name\tstart\tend\tsize\tinitialized\tread\twrite\texecute\n");
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            blocks.write(tsv(
                block.getName(), block.getStart(), block.getEnd(),
                hex(block.getSize()), block.isInitialized(), block.isRead(),
                block.isWrite(), block.isExecute()));
        }
        blocks.close();
    }

    private void exportStrings() throws Exception {
        BufferedWriter out = writer("strings.tsv");
        out.write("label\trva\tascii\n");
        for (StringAnchor anchor : STRING_ANCHORS) {
            out.write(tsv(
                anchor.label, sampRva(anchor.address),
                asciiZ(toAddr(anchor.address), 160)));
        }
        out.close();
    }

    private void exportRawSpans() throws Exception {
        BufferedWriter out = writer("raw_spans.tsv");
        out.write("label\tstart_rva\tsize\tbytes\n");
        for (RawSpan span : SAMP_RAW_SPANS) {
            out.write(tsv(
                span.label, sampRva(span.address), hex(span.size),
                bytes(toAddr(span.address), span.size)));
        }
        out.close();
    }

    private void verifyGtaPatchGuards(File patchTable) throws Exception {
        BufferedWriter out = writer("gta_patch_guards.tsv");
        out.write(
            "table\tindex\ttarget_va\texpected_opcode\tactual_opcode"
                + "\topcode_match\toperand_va\texpected_original_value"
                + "\tactual_original_value\tvalue_match\tinstruction_va"
                + "\tinstruction_bytes\tinstruction\traw_guard_bytes\n");

        BufferedReader in = new BufferedReader(new FileReader(patchTable));
        String line = in.readLine();
        while ((line = in.readLine()) != null && !monitor.isCancelled()) {
            String[] columns = line.split("\\t", -1);
            if (columns.length < 9) {
                continue;
            }
            String table = columns[0];
            if (!"model_pointer_us1".equals(table)
                    && !"atomic_store_us1".equals(table)) {
                continue;
            }

            int index = Integer.parseInt(columns[1]);
            long target = parseHex(columns[3]);
            String expectedOpcode = columns[4];
            int operandOffset = Integer.parseInt(columns[5]);
            long expectedValue = parseHex(columns[6]);
            Address targetAddress = toAddr(target);

            if ("atomic_store_us1".equals(table)) {
                Instruction instruction =
                    currentProgram.getListing().getInstructionContaining(
                        targetAddress);
                long actualValue = unsignedInt(targetAddress);
                out.write(tsv(
                    table, index, va(target), "", "", true, va(target),
                    va(expectedValue), va(actualValue),
                    actualValue == expectedValue,
                    instruction == null ? "" : va(
                        instruction.getAddress().getOffset()),
                    instruction == null ? "" : bytes(instruction),
                    instruction == null ? "" : instruction,
                    bytes(targetAddress, 4)));
                continue;
            }

            int expectedOpcodeValue =
                Integer.parseInt(expectedOpcode, 16);
            int actualOpcode =
                currentProgram.getMemory().getByte(targetAddress) & 0xff;
            Address operandAddress = targetAddress.add(operandOffset);
            long actualValue = unsignedInt(operandAddress);
            Instruction instruction =
                currentProgram.getListing().getInstructionAt(targetAddress);
            out.write(tsv(
                table, index, va(target), expectedOpcode,
                String.format("%02x", actualOpcode),
                actualOpcode == expectedOpcodeValue, va(
                    operandAddress.getOffset()), va(expectedValue),
                va(actualValue), actualValue == expectedValue,
                instruction == null ? "" : va(
                    instruction.getAddress().getOffset()),
                instruction == null ? "" : bytes(instruction),
                instruction == null ? "" : instruction,
                bytes(targetAddress, 8)));
        }
        in.close();
        out.close();

        BufferedWriter fixed = writer("gta_fixed_guards.tsv");
        fixed.write(
            "label\ttarget_va\texpected_bytes\tactual_bytes\tmatch\n");
        for (FixedGuard guard : GTA_FIXED_GUARDS) {
            Address address = toAddr(guard.address);
            int byteCount = guard.expectedBytes.length() / 2;
            String actual = bytes(address, byteCount);
            fixed.write(tsv(
                guard.label, va(guard.address), guard.expectedBytes, actual,
                guard.expectedBytes.equals(actual)));
        }
        fixed.close();
    }

    private int operandOffsetForOpcode(int opcode) {
        if (opcode == 0x8b || opcode == 0x89 || opcode == 0x39) {
            return 3;
        }
        if (opcode == 0xbe || opcode == 0xbf) {
            return 1;
        }
        return -1;
    }

    private long unsignedInt(Address address) throws Exception {
        return currentProgram.getMemory().getInt(address) & 0xffffffffL;
    }

    private String asciiZ(Address address, int limit) throws Exception {
        StringBuilder out = new StringBuilder();
        for (int index = 0; index < limit; index++) {
            int value =
                currentProgram.getMemory().getByte(address.add(index)) & 0xff;
            if (value == 0) {
                break;
            }
            if (value >= 0x20 && value <= 0x7e) {
                out.append((char)value);
            }
            else {
                out.append(String.format("\\x%02x", value));
            }
        }
        return out.toString();
    }

    private BufferedWriter writer(String name) throws Exception {
        return new BufferedWriter(new FileWriter(new File(outDir, name)));
    }

    private String bytes(Instruction instruction) throws Exception {
        return hexBytes(instruction.getBytes());
    }

    private String bytes(Address address, int count) throws Exception {
        byte[] values = new byte[count];
        currentProgram.getMemory().getBytes(address, values);
        return hexBytes(values);
    }

    private String hexBytes(byte[] values) {
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
                .replace("\n", "\\n")
                .replace("\r", "\\r"));
        }
        out.append('\n');
        return out.toString();
    }

    private long parseHex(String value) {
        String normalized = value.trim().toLowerCase();
        if (normalized.startsWith("external:")) {
            normalized = normalized.substring("external:".length());
        }
        if (normalized.startsWith("samp.dll+")) {
            return SAMP_IMAGE_BASE
                + Long.parseUnsignedLong(
                    normalized.substring("samp.dll+".length() + 2), 16);
        }
        if (normalized.startsWith("0x")) {
            normalized = normalized.substring(2);
        }
        return Long.parseUnsignedLong(normalized, 16);
    }

    private String sampRva(long address) {
        if (address < SAMP_IMAGE_BASE || address >= 0x20000000L) {
            return "external:" + va(address);
        }
        return String.format("samp.dll+0x%08x", address - SAMP_IMAGE_BASE);
    }

    private String va(long address) {
        return String.format("0x%08x", address);
    }

    private String hex(long value) {
        return String.format("0x%x", value);
    }
}
