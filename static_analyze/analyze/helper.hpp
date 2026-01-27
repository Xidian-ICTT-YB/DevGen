#ifndef HELPER_HPP
#define HELPER_HPP

// Standard library includes
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <map>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <tuple>
#include <unistd.h>
#include <vector>

// JSON library
#include "json.hpp"

// Clang includes
#include "clang/AST/Decl.h"
#include "clang/AST/TemplateName.h"
#include "clang/ASTMatchers/ASTMatchers.h"
#include "clang/Rewrite/Core/Rewriter.h"
#include <clang/AST/ASTConsumer.h>
#include <clang/AST/ASTContext.h>
#include <clang/AST/Expr.h>
#include <clang/AST/RecursiveASTVisitor.h>
#include <clang/Frontend/CompilerInstance.h>
#include <clang/Frontend/FrontendActions.h>
#include <clang/Tooling/CommonOptionsParser.h>
#include <clang/Tooling/JSONCompilationDatabase.h>
#include <clang/Tooling/Tooling.h>

/**
 * @class Semaphore
 * @brief Simple semaphore implementation for thread synchronization
 */
class Semaphore {
public:
  explicit Semaphore(int count) : m_count(count) {}

  /**
   * @brief Notify (signal) the semaphore
   */
  inline void notify() {
    std::unique_lock<std::mutex> lock(m_mutex);
    m_count++;
    m_conditionVariable.notify_one();
  }

  /**
   * @brief Wait for the semaphore
   */
  inline void wait() {
    std::unique_lock<std::mutex> lock(m_mutex);
    while (m_count == 0) {
      m_conditionVariable.wait(lock);
    }
    m_count--;
  }

private:
  std::mutex m_mutex;
  std::condition_variable m_conditionVariable;
  int m_count;
};

// ============================================================================
// Declaration collection functions
// ============================================================================

/**
 * @brief Get filename with line number from source location
 * @param location Source location
 * @param sourceManager Source manager
 * @return String in format "filename:line"
 */
std::string getFilenameWithLine(clang::SourceLocation location, 
                                clang::SourceManager &sourceManager);

/**
 * @brief Get source code for a declaration
 * @param decl The named declaration
 * @return Source code as string
 */
std::string get_decl_code(const clang::NamedDecl *decl);

/**
 * @brief Output a declaration to JSONL file
 * @param decl The named declaration
 * @param outputFileName Output file name
 * @param isTypedef Whether this is a typedef declaration
 * @param aliasName Alias name for typedefs
 */
void output_decl(const clang::NamedDecl *decl, 
                 std::string outputFileName,
                 bool isTypedef = false, 
                 std::string aliasName = "");

/**
 * @brief Output a macro definition to JSONL file
 * @param macroName Macro name
 * @param sourceCode Macro source code
 * @param filename File name with line number
 * @param outputFileName Output file name
 */
void output_define(std::string macroName, 
                   std::string sourceCode, 
                   std::string filename, 
                   std::string outputFileName);

/**
 * @brief Output a variable declaration to JSONL file
 * @param decl The named declaration
 * @param outputFileName Output file name
 * @param typeName Variable type name
 */
void output_var_decl(const clang::NamedDecl *decl, 
                     std::string outputFileName, 
                     std::string typeName);


#endif // HELPER_HPP
