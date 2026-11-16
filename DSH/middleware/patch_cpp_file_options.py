#!/usr/bin/env python3
"""Add per-file ARM Compiler 6 options to C++ sources in STM32H743.uvprojx.

uVision 5.24's C++ standard selector tops out below C++17 while TGX needs
`if constexpr` / `template<auto>`, so the standard is forced per file.

The <FileOption> block below mirrors the schema uVision itself writes (a full
<Cads> section with "2 = inherit" values); an incomplete block makes uVision
leak the options into unrelated compiles (observed: assembler got -std=c++1z).

Usage (from project root):
    python DSH/middleware/patch_cpp_file_options.py Color.cpp Fonts.cpp ...
"""
import io
import re
import sys

PATH = "Projects/MDK-ARM/STM32H743.uvprojx"
FLAGS = "-std=c++1z -fno-exceptions -fno-rtti"

FILE_OPTION = """              <FileOption>
                <CommonProperty>
                  <UseCPPCompiler>2</UseCPPCompiler>
                  <RVCTCodeConst>0</RVCTCodeConst>
                  <RVCTZI>0</RVCTZI>
                  <RVCTOtherData>0</RVCTOtherData>
                  <ModuleSelection>0</ModuleSelection>
                  <IncludeInBuild>1</IncludeInBuild>
                  <AlwaysBuild>2</AlwaysBuild>
                  <GenerateAssemblyFile>2</GenerateAssemblyFile>
                  <AssembleAssemblyFile>2</AssembleAssemblyFile>
                  <PublicsOnly>2</PublicsOnly>
                  <StopOnExitCode>11</StopOnExitCode>
                  <CustomArgument></CustomArgument>
                  <IncludeLibraryModules></IncludeLibraryModules>
                  <ComprImg>1</ComprImg>
                </CommonProperty>
                <FileArmAds>
                  <Cads>
                    <interw>2</interw>
                    <Optim>0</Optim>
                    <oTime>2</oTime>
                    <SplitLS>2</SplitLS>
                    <OneElfS>2</OneElfS>
                    <Strict>2</Strict>
                    <EnumInt>2</EnumInt>
                    <PlainCh>2</PlainCh>
                    <Ropi>2</Ropi>
                    <Rwpi>2</Rwpi>
                    <wLevel>0</wLevel>
                    <uThumb>2</uThumb>
                    <uSurpInc>2</uSurpInc>
                    <uC99>2</uC99>
                    <uGnu>2</uGnu>
                    <useXO>2</useXO>
                    <v6Lang>0</v6Lang>
                    <v6LangP>0</v6LangP>
                    <vShortEn>2</vShortEn>
                    <vShortWch>2</vShortWch>
                    <v6Lto>2</v6Lto>
                    <v6WtE>2</v6WtE>
                    <v6Rtti>2</v6Rtti>
                    <VariousControls>
                      <MiscControls>@@FLAGS@@</MiscControls>
                      <Define></Define>
                      <Undefine></Undefine>
                      <IncludePath></IncludePath>
                    </VariousControls>
                  </Cads>
                </FileArmAds>
              </FileOption>
""".replace("@@FLAGS@@", FLAGS)


def main():
    names = sys.argv[1:]
    if not names:
        raise SystemExit("usage: patch_cpp_file_options.py FILE.cpp [FILE.cpp ...]")

    s = io.open(PATH, encoding="latin-1").read()
    changed = 0

    for name in names:
        pat = re.compile(r"(<File>\s*<FileName>%s</FileName>.*?</FilePath>\s*)(</File>)" % re.escape(name), re.S)
        m = pat.search(s)
        if not m:
            print("  ! entry not found:", name)
            continue

        block = m.group(1)
        block = re.sub(r"\s*<FileOption>.*?</FileOption>\s*", "\n", block, count=1, flags=re.S)

        new_block = block.rstrip() + "\n" + FILE_OPTION
        s = s[:m.start(1)] + new_block + s[m.start(2):]
        changed += 1
        print("  patched:", name)

    io.open(PATH, "w", encoding="latin-1", newline="").write(s)
    print("done,", changed, "file(s)")


if __name__ == "__main__":
    main()
