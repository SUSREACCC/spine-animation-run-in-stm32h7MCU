#!/usr/bin/env python3
"""Add the spine-cpp runtime (Middlewares/SPINE) to STM32H743.uvprojx.

Creates a "Middlewares/SPINE" group with every src/spine/*.cpp file, a
group-level option block (C++17, -O3, no exceptions/RTTI, include path) and
registers Middlewares\\SPINE\\include on the target include path.

Run from the project root:  python DSH/middleware/patch_add_spine.py
"""
import io
import os

PATH = "Projects/MDK-ARM/STM32H743.uvprojx"
SRC_DIR = "Middlewares/SPINE/src/spine"
GROUP_NAME = "Middlewares/SPINE"

GROUP_OPTION = """          <GroupOption>
            <CommonProperty>
              <UseCPPCompiler>0</UseCPPCompiler>
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
            <GroupArmAds>
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
                <wLevel>1</wLevel>
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
                  <MiscControls>-std=c++1z -O3 -fno-exceptions -fno-rtti</MiscControls>
                  <Define></Define>
                  <Undefine></Undefine>
                  <IncludePath>..\\..\\Middlewares\\SPINE\\include</IncludePath>
                </VariousControls>
              </Cads>
            </GroupArmAds>
          </GroupOption>
"""


def main():
    s = io.open(PATH, encoding="latin-1").read()
    if GROUP_NAME in s:
        print("spine group already present")
        return

    files = sorted(f for f in os.listdir(SRC_DIR) if f.endswith(".cpp"))
    body = []
    for f in files:
        body.append(
            "            <File>\n"
            "              <FileName>%s</FileName>\n"
            "              <FileType>8</FileType>\n"
            "              <FilePath>..\\..\\Middlewares\\SPINE\\src\\spine\\%s</FilePath>\n"
            "            </File>\n" % (f, f)
        )

    group = (
        "        <Group>\n"
        "          <GroupName>%s</GroupName>\n"
        "%s"
        "          <Files>\n"
        "%s"
        "          </Files>\n"
        "        </Group>\n" % (GROUP_NAME, GROUP_OPTION, "".join(body))
    )

    s = s.replace("      </Groups>", group + "      </Groups>", 1)

    # include path on the target (Cads of the target)
    if "Middlewares\\\\SPINE\\\\include" not in s and "Middlewares\\SPINE\\include" not in s:
        s = s.replace("<IncludePath>", "<IncludePath>..\\..\\Middlewares\\SPINE\\include;", 1)

    io.open(PATH, "w", encoding="latin-1", newline="").write(s)
    print("added %d spine sources" % len(files))


if __name__ == "__main__":
    main()
