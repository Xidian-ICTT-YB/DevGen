#include "helper.hpp"

using namespace clang;
using namespace clang::tooling;
using json = nlohmann::json;

// Global synchronization primitives
std::mutex g_mutex;
std::set<std::string> g_existingFilenames;

// ============================================================================
// Helper functions
// ============================================================================

/**
 * @brief Get filename with line number from source location
 * @param location Source location
 * @param sourceManager Source manager
 * @return String in format "filename:line"
 */
std::string getFilenameWithLine(SourceLocation location, 
                                SourceManager &sourceManager) {
    std::stringstream filenameWithLine;
    if (const FileEntry *fileEntry = 
            sourceManager.getFileEntryForID(sourceManager.getFileID(location))) {
        filenameWithLine << fileEntry->tryGetRealPathName().str();
    } else {
        filenameWithLine << location.printToString(sourceManager);
    }
    // Append line number
    unsigned lineNumber = sourceManager.getSpellingLineNumber(location);
    filenameWithLine << ":" << lineNumber;
    return filenameWithLine.str();
}

/**
 * @brief Check if an entry already exists to avoid duplicates
 * @param key Unique key for the entry
 * @return True if entry already exists
 */
static bool entryExists(const std::string &key) {
    return g_existingFilenames.find(key) != g_existingFilenames.end();
}

/**
 * @brief Add an entry to the existing entries set
 * @param key Unique key for the entry
 */
static void addEntry(const std::string &key) {
    g_existingFilenames.insert(key);
}

// ============================================================================
// Public functions implementation
// ============================================================================

/**
 * @brief Get source code for a declaration
 */
std::string get_decl_code(const NamedDecl *decl) {
    SourceManager &sourceManager = decl->getASTContext().getSourceManager();
    SourceLocation startLoc = decl->getBeginLoc();
    SourceLocation endLoc = decl->getEndLoc();

    if (startLoc.isInvalid() || endLoc.isInvalid()) {
        return "";
    }

    // Convert the source locations to file locations
    startLoc = sourceManager.getSpellingLoc(startLoc);
    endLoc = sourceManager.getSpellingLoc(endLoc);

    // Extract the source code text
    bool invalid = false;
    StringRef text = Lexer::getSourceText(
        CharSourceRange::getTokenRange(startLoc, endLoc),
        sourceManager, 
        LangOptions(), 
        &invalid
    );

    if (!invalid) {
        return text.str();
    }
    
    return "";
}

/**
 * @brief Output a declaration to JSONL file
 */
void output_decl(const NamedDecl *decl, 
                 std::string outputFileName,
                 bool isTypedef, 
                 std::string aliasName) {
    std::lock_guard<std::mutex> lock(g_mutex);

    std::string name = decl->getNameAsString();
    std::string sourceCode = get_decl_code(decl);
    
    if (name.empty()) {
        return;
    }

    // Get filename with line number
    SourceLocation beginLoc = decl->getBeginLoc();
    SourceManager &sourceManager = decl->getASTContext().getSourceManager();
    std::string filename = getFilenameWithLine(beginLoc, sourceManager);

    // Create unique key to avoid duplicates
    std::string key = filename + "+" + name + "+" + outputFileName + "+" + aliasName;
    if (entryExists(key)) {
        return;
    }
    addEntry(key);

    // Create JSON object
    json jsonObj;
    jsonObj["name"] = name;
    jsonObj["source"] = sourceCode;
    jsonObj["filename"] = filename;

    if (isTypedef && !aliasName.empty()) {
        jsonObj["alias"] = aliasName;
    }

    // Write to file
    std::ofstream outputFile;
    outputFile.open(outputFileName, std::ios_base::app);
    outputFile << jsonObj.dump() << std::endl;
    outputFile.flush();
    outputFile.close();
}

/**
 * @brief Output a macro definition to JSONL file
 */
void output_define(std::string macroName, 
                   std::string sourceCode, 
                   std::string filename, 
                   std::string outputFileName) {
    std::lock_guard<std::mutex> lock(g_mutex);

    if (macroName.empty()) {
        return;
    }

    // Create unique key to avoid duplicates
    std::string key = filename + "+" + macroName + "+" + outputFileName;
    if (entryExists(key)) {
        return;
    }
    addEntry(key);

    // Create JSON object
    json jsonObj;
    jsonObj["name"] = macroName;
    jsonObj["source"] = "#define " + sourceCode;
    jsonObj["filename"] = filename;

    // Write to file
    std::ofstream outputFile;
    outputFile.open(outputFileName, std::ios_base::app);
    outputFile << jsonObj.dump() << std::endl;
    outputFile.flush();
    outputFile.close();
}

/**
 * @brief Output a variable declaration to JSONL file
 */
void output_var_decl(const NamedDecl *decl, 
                     std::string outputFileName, 
                     std::string typeName) {
    std::lock_guard<std::mutex> lock(g_mutex);

    std::string name = decl->getNameAsString();
    std::string sourceCode = get_decl_code(decl);
    
    if (name.empty()) {
        return;
    }

    // Get filename with line number
    SourceLocation beginLoc = decl->getBeginLoc();
    SourceManager &sourceManager = decl->getASTContext().getSourceManager();
    std::string filename = getFilenameWithLine(beginLoc, sourceManager);

    // Create unique key to avoid duplicates
    std::string key = filename + "+" + name + "+" + outputFileName;
    if (entryExists(key)) {
        return;
    }
    addEntry(key);

    // Create JSON object
    json jsonObj;
    jsonObj["name"] = name;
    jsonObj["source"] = sourceCode;
    jsonObj["type"] = typeName;
    jsonObj["filename"] = filename;

    // Write to file
    std::ofstream outputFile;
    outputFile.open(outputFileName, std::ios_base::app);
    outputFile << jsonObj.dump() << std::endl;
    outputFile.flush();
    outputFile.close();
}
