## ⚙️  Driver Information Collection

Before you start, please make sure that you have installed and configured the following items:

1.  **Python:** \>= 3.8.10
2.  **Git and Git Submodules:** Cloning the Repository and Its Dependencies.
Clone the repository and its dependencies.
3.  **Construction tools:** 
    
    ```bash
    sudo apt-get update && sudo apt-get install build-essential make bear git
    ```
4.  **Clang:** The analysis tools require versions 14 and 15.
    
    ```bash
    sudo apt-get install clang-15 libclang-15-dev clang-14 libclang-14-dev
    # Ensure clang-15 is the default or adjust paths in subsequent steps
    # Example: export CC=clang-15 CXX=clang++-15
    ```
```
    
5.  **Source of Linux Kernel:** You need a local copy of the Linux kernel source code that you intend to analyze.

## 🛠️ install

### Step 1: Kernel Preparation & Static Analysis

This step involves analyzing the Linux kernel source code to extract the necessary information for LLM.

1.  **Navigate to the Linux sub-module:**

    ```bash
    cd linux
```

2.  **Configure the kernel:** It is recommended to use the configuration `allyesconfig` to achieve comprehensive analysis coverage.

    ```bash
    git clone https://github.com/torvalds/linux.git
    git checkout v6.18
    make CC=clang-15 HOSTCC=clang-15 allyesconfig
    ```

3.  **Use `bear` build kernel:** This program intercepts the compiler calls to generate`compile_commands.json`.

    ```
    bear make CC=clang-15 HOSTCC=clang-15 -j$(nproc)
    ```

    **Will generate `compile_commands.json` in`linux/`.**

4.  Build analyzer tool:**

    ```bash
    cd ../analyzer
    # Ensure Clang-15 dev libraries are installed and accessible
    make analyze
    ```

    **This will create `analyze` executable file.**

5.  **Operation Analysis and Processing:**

    ```bash
    cd ../linux
    python ../analyzer/feliter.py compile_commands.json compile_commands_filtered.json
    ../analyzer/analyze -p compile_commands_filtered.json
    
    cd ../split
    python split_json.py
    ```
