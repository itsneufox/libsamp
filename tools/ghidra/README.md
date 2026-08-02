# Local Ghidra Setup

Persistent Ghidra install:

```bash
/home/chairman/Projects/sa-mp.dll-rebuild/tools/ghidra/run-ghidra.sh
```

Headless analyzer:

```bash
/home/chairman/Projects/sa-mp.dll-rebuild/tools/ghidra/analyze-headless.sh
```

GhidraMCP extension ZIP inside the install:

```bash
/home/chairman/Projects/sa-mp.dll-rebuild/tools/ghidra/ghidra_12.1.2_PUBLIC/ghidra_12.1.2_PUBLIC/Extensions/Ghidra/GhidraMCP-2.0-ghidra12.zip
```

The wrappers set `JAVA_HOME` to the local JDK 21 copy:

```bash
/home/chairman/Projects/sa-mp.dll-rebuild/tools/ghidra/jdk-21.0.11+10
```

They also keep Ghidra config/cache local to `tools/ghidra/.config` and
`tools/ghidra/.cache`.
