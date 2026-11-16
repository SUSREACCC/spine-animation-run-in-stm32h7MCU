#!/usr/bin/env python3
"""Rebuild the <File> entries of the C++ sources so each carries a complete,
uVision-valid per-file option block (C++17 flags, included in build).

This replaces the whole <File>...</File> block for each name instead of doing
regex surgery inside it, which previously produced misnested entries.

Run from the project root:
    python DSH/middleware/rebuild_cpp_entries.py
"""
import io
import re

PATH = "Projects/MDK-ARM/STM32H743.uvprojx"
FLAGS = "-std=c++1z -O3 -fno-exceptions -fno-rtti"
NAMES = ["Color.cpp", "Fonts.cpp", "tgx_selftest.cpp", "raster_probe.cpp",
         "raster2d.cpp", "raster_test.cpp", "spine_platform.cpp"]

BLOCK = """            <File>
              <FileName>@@NAME@@</FileName>
              <FileType>8</FileType>
              <FilePath>@@PATH@@</FilePath>
              <FileOption>
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
            </File>"""


def main():
    s = io.open(PATH, encoding="latin-1").read()
    done = []

    for name in NAMES:
        pat = re.compile(r"<File>\s*<FileName>%s</FileName>.*?</File>" % re.escape(name), re.S)
        m = pat.search(s)
        if not m:
            print("  ! not found:", name)
            continue

        pm = re.search(r"<FilePath>(.*?)</FilePath>", m.group(0), re.S)
        path = pm.group(1) if pm else ""

        block = BLOCK.replace("@@NAME@@", name).replace("@@PATH@@", path).replace("@@FLAGS@@", FLAGS)
        s = s[:m.start()] + block + s[m.end():]
        done.append(name)

    io.open(PATH, "w", encoding="latin-1", newline="").write(s)
    print("rebuilt entries:", ", ".join(done))


if __name__ == "__main__":
    main()
