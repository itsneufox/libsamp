// Ghidra headless export script for the original SA-MP 0.3.7 samp.dll.
// STATIC_037: emits metadata and cross-reference summaries only; it does not
// export decompiler pseudocode or copied proprietary control-flow bodies.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.data.DataType;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.ExternalLocation;
import ghidra.program.model.symbol.ExternalManager;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.program.model.symbol.RefType;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.program.model.symbol.SymbolTable;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ExportSampAnalysis extends GhidraScript {
    private static final long IMAGE_BASE = 0x10000000L;

    private static final Set<String> FOCUS_IMPORTS = new HashSet<String>(Arrays.asList(
        "WSAStartup", "WSACleanup", "socket", "connect", "bind", "listen",
        "accept", "send", "recv", "sendto", "recvfrom", "closesocket",
        "ioctlsocket", "setsockopt", "getsockname", "gethostbyname",
        "gethostname", "inet_addr", "inet_ntoa", "htons", "ntohs",
        "Direct3DCreate9", "D3DXCreateFontA", "D3DXCreateSprite",
        "D3DXCreateTextureFromFileInMemory", "D3DXCreateTextureFromFileA",
        "BASS_Init", "BASS_StreamCreateURL", "BASS_StreamFree",
        "BASS_ChannelPlay", "BASS_ChannelStop", "BASS_ChannelSetAttribute",
        "CreateFileA", "ReadFile", "WriteFile", "CreateThread",
        "VirtualProtect", "FlushInstructionCache", "LoadLibraryA",
        "GetProcAddress", "CreateWindowExA", "PeekMessageA", "GetAsyncKeyState"
    ));

    private File outDir;
    private Listing listing;
    private ReferenceManager refman;

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException("usage: ExportSampAnalysis.java <output-dir>");
        }
        outDir = new File(args[0]);
        Files.createDirectories(outDir.toPath());
        listing = currentProgram.getListing();
        refman = currentProgram.getReferenceManager();

        exportSummary();
        exportMemoryBlocks();
        exportFunctions();
        exportImportsAndXrefs();
        exportStrings();
        exportFocusCallers();
        exportCallgraphSlices();
    }

    private void exportSummary() throws Exception {
        BufferedWriter w = writer("summary.md");
        w.write("# Ghidra Static Analysis Summary\n\n");
        w.write("- Evidence: `STATIC_037`\n");
        w.write("- Program: `" + esc(currentProgram.getName()) + "`\n");
        w.write("- Executable SHA-256: `" + sha256(new File(currentProgram.getExecutablePath())) + "`\n");
        w.write("- Ghidra language: `" + esc(currentProgram.getLanguageID().toString()) + "`\n");
        w.write("- Compiler spec: `" + esc(currentProgram.getCompilerSpec().getCompilerSpecID().toString()) + "`\n");
        w.write("- Image base: `" + currentProgram.getImageBase() + "`\n");
        w.write("- Entry point: `" + currentProgram.getSymbolTable().getExternalEntryPointIterator().hasNext() + "` external-entry marker present\n");
        w.write("- Min address: `" + currentProgram.getMinAddress() + "`\n");
        w.write("- Max address: `" + currentProgram.getMaxAddress() + "`\n");
        w.write("- Function count: `" + countFunctions() + "`\n");
        w.write("- Symbol count: `" + countSymbols() + "`\n");
        w.write("\nNotes:\n");
        w.write("- No decompiler pseudocode is exported by this script.\n");
        w.write("- RVAs assume the original preferred image base `0x10000000`.\n");
        w.close();
    }

    private void exportMemoryBlocks() throws Exception {
        BufferedWriter w = writer("memory_blocks.tsv");
        w.write("name\tstart\tend\trva_start\trva_end\tsize\trwx\tinitialized\n");
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            String rwx = (block.isRead() ? "r" : "-") + (block.isWrite() ? "w" : "-") + (block.isExecute() ? "x" : "-");
            w.write(tsv(block.getName(), block.getStart(), block.getEnd(), rva(block.getStart()), rva(block.getEnd()),
                block.getSize(), rwx, block.isInitialized()));
        }
        w.close();
    }

    private void exportFunctions() throws Exception {
        BufferedWriter all = writer("functions.tsv");
        BufferedWriter top = writer("top_functions.tsv");
        all.write("entry\trva\tname\tsize\tbody_ranges\tcall_in\tcall_out\tdata_refs_from\tis_thunk\tcalling_convention\n");
        List<FunctionRow> rows = new ArrayList<FunctionRow>();
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Function f = it.next();
            FunctionRow row = functionRow(f);
            rows.add(row);
            all.write(row.toTsv());
        }
        all.close();

        Collections.sort(rows, new Comparator<FunctionRow>() {
            public int compare(FunctionRow a, FunctionRow b) {
                return Long.compare(b.size, a.size);
            }
        });
        top.write("entry\trva\tname\tsize\tbody_ranges\tcall_in\tcall_out\tdata_refs_from\tis_thunk\tcalling_convention\n");
        for (int i = 0; i < Math.min(250, rows.size()); i++) {
            top.write(rows.get(i).toTsv());
        }
        top.close();
    }

    private void exportImportsAndXrefs() throws Exception {
        BufferedWriter imports = writer("imports.tsv");
        BufferedWriter xrefs = writer("import_xrefs.tsv");
        imports.write("library\tlabel\taddress\trva\tref_count\tfocus\n");
        xrefs.write("library\tlabel\timport_address\tfrom_function\tfrom_entry\tfrom_rva\tref_type\toperand_index\n");

        ExternalManager em = currentProgram.getExternalManager();
        SymbolTable st = currentProgram.getSymbolTable();
        SymbolIterator symbols = st.getExternalSymbols();
        while (symbols.hasNext() && !monitor.isCancelled()) {
            Symbol sym = symbols.next();
            Address addr = sym.getAddress();
            if (addr == null) {
                continue;
            }
            String lib = "";
            ExternalLocation loc = em.getExternalLocation(sym);
            if (loc != null && loc.getLibraryName() != null) {
                lib = loc.getLibraryName();
            }
            String label = sym.getName();
            ReferenceIterator refs = refman.getReferencesTo(addr);
            List<Reference> refList = new ArrayList<Reference>();
            while (refs.hasNext()) {
                refList.add(refs.next());
            }
            imports.write(tsv(lib, label, addr, rva(addr), refList.size(), FOCUS_IMPORTS.contains(label)));
            for (Reference ref : refList) {
                Address from = ref.getFromAddress();
                Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
                xrefs.write(tsv(lib, label, addr, f == null ? "" : f.getName(), f == null ? "" : f.getEntryPoint(),
                    rva(from), ref.getReferenceType(), ref.getOperandIndex()));
            }
        }
        imports.close();
        xrefs.close();
    }

    private void exportStrings() throws Exception {
        BufferedWriter strings = writer("strings.tsv");
        BufferedWriter refs = writer("string_xrefs.tsv");
        strings.write("address\trva\tlength\tdatatype\tvalue\n");
        refs.write("string_address\tstring_rva\tfrom_function\tfrom_entry\tfrom_rva\tref_type\tvalue\n");

        Iterator<Data> it = listing.getDefinedData(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Data data = it.next();
            if (!isStringData(data)) {
                continue;
            }
            String value = String.valueOf(data.getValue());
            if (value.length() < 4) {
                continue;
            }
            strings.write(tsv(data.getAddress(), rva(data.getAddress()), data.getLength(),
                data.getDataType().getName(), value));
            ReferenceIterator rit = refman.getReferencesTo(data.getAddress());
            while (rit.hasNext()) {
                Reference ref = rit.next();
                Address from = ref.getFromAddress();
                Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
                refs.write(tsv(data.getAddress(), rva(data.getAddress()), f == null ? "" : f.getName(),
                    f == null ? "" : f.getEntryPoint(), rva(from), ref.getReferenceType(), value));
            }
        }
        strings.close();
        refs.close();
    }

    private void exportFocusCallers() throws Exception {
        BufferedWriter w = writer("focus_import_callers.tsv");
        w.write("focus\tlibrary\tcaller\tcaller_entry\tcaller_rva\tcallsite\tcallsite_rva\tref_type\n");
        SymbolIterator symbols = currentProgram.getSymbolTable().getExternalSymbols();
        while (symbols.hasNext() && !monitor.isCancelled()) {
            Symbol sym = symbols.next();
            if (!FOCUS_IMPORTS.contains(sym.getName())) {
                continue;
            }
            ExternalLocation loc = currentProgram.getExternalManager().getExternalLocation(sym);
            String lib = (loc == null || loc.getLibraryName() == null) ? "" : loc.getLibraryName();
            for (Reference ref : refman.getReferencesTo(sym.getAddress())) {
                Function f = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                w.write(tsv(sym.getName(), lib, f == null ? "" : f.getName(), f == null ? "" : f.getEntryPoint(),
                    f == null ? "" : rva(f.getEntryPoint()), ref.getFromAddress(), rva(ref.getFromAddress()),
                    ref.getReferenceType()));
            }
        }
        w.close();
    }

    private void exportCallgraphSlices() throws Exception {
        BufferedWriter w = writer("priority_callgraph.tsv");
        w.write("seed\tseed_rva\tdirection\tdepth\tfunction\tfunction_entry\tfunction_rva\tcallee_or_caller\tpeer_entry\tpeer_rva\tref_type\n");
        long[] seeds = new long[] {
            0x100cbc90L, 0x100cbb0fL, 0x100c5270L, 0x100c50c0L,
            0x10053820L, 0x10053850L, 0x10053870L, 0x100538b0L,
            0x100539c0L, 0x10053a00L, 0x10053ab0L, 0x10053b40L,
            0x10053b70L, 0x10053bf0L, 0x10055e60L, 0x10055ff0L,
            0x10056880L, 0x10095d10L, 0x1006b8e0L, 0x10092370L,
            0x1007fcf0L, 0x10066480L
        };
        for (long seed : seeds) {
            Function f = functionAt(seed);
            if (f == null) {
                continue;
            }
            emitOutgoing(w, f, f, 0, new HashSet<Address>());
            emitIncoming(w, f, f, 0, new HashSet<Address>());
        }
        w.close();
    }

    private void emitOutgoing(BufferedWriter w, Function seed, Function f, int depth, Set<Address> seen) throws Exception {
        if (depth > 2 || f == null || !seen.add(f.getEntryPoint())) {
            return;
        }
        InstructionIterator it = listing.getInstructions(f.getBody(), true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction insn = it.next();
            for (Reference ref : insn.getReferencesFrom()) {
                if (!ref.getReferenceType().isCall()) {
                    continue;
                }
                Function callee = currentProgram.getFunctionManager().getFunctionAt(ref.getToAddress());
                if (callee == null) {
                    callee = currentProgram.getFunctionManager().getFunctionContaining(ref.getToAddress());
                }
                if (callee == null) {
                    continue;
                }
                w.write(tsv(seed.getName(), rva(seed.getEntryPoint()), "out", depth, f.getName(), f.getEntryPoint(),
                    rva(f.getEntryPoint()), callee.getName(), callee.getEntryPoint(), rva(callee.getEntryPoint()),
                    ref.getReferenceType()));
                emitOutgoing(w, seed, callee, depth + 1, seen);
            }
        }
    }

    private void emitIncoming(BufferedWriter w, Function seed, Function f, int depth, Set<Address> seen) throws Exception {
        if (depth > 2 || f == null || !seen.add(f.getEntryPoint())) {
            return;
        }
        ReferenceIterator refs = refman.getReferencesTo(f.getEntryPoint());
        while (refs.hasNext() && !monitor.isCancelled()) {
            Reference ref = refs.next();
            if (!ref.getReferenceType().isCall()) {
                continue;
            }
            Function caller = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            if (caller == null) {
                continue;
            }
            w.write(tsv(seed.getName(), rva(seed.getEntryPoint()), "in", depth, f.getName(), f.getEntryPoint(),
                rva(f.getEntryPoint()), caller.getName(), caller.getEntryPoint(), rva(caller.getEntryPoint()),
                ref.getReferenceType()));
            emitIncoming(w, seed, caller, depth + 1, seen);
        }
    }

    private FunctionRow functionRow(Function f) {
        AddressSetView body = f.getBody();
        int callOut = 0;
        int dataRefsFrom = 0;
        InstructionIterator it = listing.getInstructions(body, true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction insn = it.next();
            for (Reference ref : insn.getReferencesFrom()) {
                RefType type = ref.getReferenceType();
                if (type.isCall()) {
                    callOut++;
                } else if (type.isData()) {
                    dataRefsFrom++;
                }
            }
        }
        int callIn = 0;
        ReferenceIterator refs = refman.getReferencesTo(f.getEntryPoint());
        while (refs.hasNext()) {
            if (refs.next().getReferenceType().isCall()) {
                callIn++;
            }
        }
        return new FunctionRow(f.getEntryPoint(), rva(f.getEntryPoint()), f.getName(), body.getNumAddresses(),
            body.toString(), callIn, callOut, dataRefsFrom, f.isThunk(), f.getCallingConventionName());
    }

    private Function functionAt(long absolute) {
        AddressSpace space = currentProgram.getAddressFactory().getDefaultAddressSpace();
        Address addr = space.getAddress(absolute);
        Function f = currentProgram.getFunctionManager().getFunctionAt(addr);
        if (f == null) {
            f = currentProgram.getFunctionManager().getFunctionContaining(addr);
        }
        return f;
    }

    private boolean isStringData(Data data) {
        DataType dt = data.getDataType();
        String name = dt == null ? "" : dt.getName().toLowerCase();
        return name.contains("string") || name.contains("unicode");
    }

    private long countFunctions() {
        long count = 0;
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        while (it.hasNext()) {
            it.next();
            count++;
        }
        return count;
    }

    private long countSymbols() {
        long count = 0;
        SymbolIterator it = currentProgram.getSymbolTable().getAllSymbols(true);
        while (it.hasNext()) {
            it.next();
            count++;
        }
        return count;
    }

    private BufferedWriter writer(String name) throws Exception {
        return new BufferedWriter(new FileWriter(new File(outDir, name)));
    }

    private static String sha256(File f) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] data = Files.readAllBytes(f.toPath());
        byte[] digest = md.digest(data);
        StringBuilder sb = new StringBuilder();
        for (byte b : digest) {
            sb.append(String.format("%02x", b & 0xff));
        }
        return sb.toString();
    }

    private static String rva(Address addr) {
        if (addr == null) {
            return "";
        }
        long off = addr.getOffset() - IMAGE_BASE;
        if (off < 0) {
            return "";
        }
        return String.format("0x%08x", off);
    }

    private static String tsv(Object... fields) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < fields.length; i++) {
            if (i > 0) {
                sb.append('\t');
            }
            sb.append(esc(String.valueOf(fields[i])));
        }
        sb.append('\n');
        return sb.toString();
    }

    private static String esc(String s) {
        if (s == null) {
            return "";
        }
        return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n");
    }

    private static class FunctionRow {
        final Address entry;
        final String rva;
        final String name;
        final long size;
        final String bodyRanges;
        final int callIn;
        final int callOut;
        final int dataRefsFrom;
        final boolean thunk;
        final String callingConvention;

        FunctionRow(Address entry, String rva, String name, long size, String bodyRanges,
                    int callIn, int callOut, int dataRefsFrom, boolean thunk, String callingConvention) {
            this.entry = entry;
            this.rva = rva;
            this.name = name;
            this.size = size;
            this.bodyRanges = bodyRanges;
            this.callIn = callIn;
            this.callOut = callOut;
            this.dataRefsFrom = dataRefsFrom;
            this.thunk = thunk;
            this.callingConvention = callingConvention;
        }

        String toTsv() {
            return tsv(entry, rva, name, size, bodyRanges, callIn, callOut, dataRefsFrom, thunk, callingConvention);
        }
    }
}
