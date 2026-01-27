#include "helper.hpp"
#include "clang/Lex/Preprocessor.h"
#include "clang/Lex/PPCallbacks.h"

using namespace clang;
using namespace clang::tooling;

/**
 * @class DefineCollector
 * @brief Collects macro definitions from preprocessor callbacks
 */
class DefineCollector : public PPCallbacks {
public:
    DefineCollector(Preprocessor &pp, bool collectDefine, SourceManager &sm) 
        : m_pp(pp), m_collectDefine(collectDefine), m_sm(sm) {}
    
    void MacroDefined(const Token &macroNameTok, const MacroDirective *md) override {
        if (!m_collectDefine) return;
        
        std::string macroName = macroNameTok.getIdentifierInfo()->getName().str();
        SourceLocation loc = md->getLocation();
        
        // Skip invalid locations
        if (loc.isInvalid()) {
            return;
        }
        
        // Get the full range of macro definition
        const MacroInfo *mi = md->getMacroInfo();
        if (mi) {
            SourceLocation start = mi->getDefinitionLoc();
            SourceLocation end = mi->getDefinitionEndLoc();
            
            if (start.isInvalid()) {
                return;
            }
            
            bool invalid = false;
            StringRef text = Lexer::getSourceText(CharSourceRange::getTokenRange(start, end), 
                                                 m_sm, LangOptions(), &invalid);
            if (!invalid) {
                std::string sourceCode = text.str();
                std::string filename = getFilenameWithLine(start, m_sm);
                output_define(macroName, sourceCode, filename, "define.jsonl");
            }
        } else {
            // Fallback to just the definition point
            bool invalid = false;
            StringRef text = Lexer::getSourceText(CharSourceRange::getTokenRange(loc, loc), 
                                                 m_sm, LangOptions(), &invalid);
            if (!invalid) {
                std::string sourceCode = text.str();
                std::string filename = getFilenameWithLine(loc, m_sm);
                output_define(macroName, sourceCode, filename, "define.jsonl");
            }
        }
    }
    
private:
    
private:
    Preprocessor &m_pp;
    bool m_collectDefine;
    SourceManager &m_sm;
};


/**
 * @class StructVisitor
 * @brief AST visitor that collects various declarations from C/C++ code
 */
class StructVisitor : public RecursiveASTVisitor<StructVisitor> {
public:
  explicit StructVisitor(ASTContext *context, 
                         bool collectEnum = true,
                         bool collectStruct = true, 
                         bool collectFunc = true,
                         bool collectTypedef = true,
                         bool collectStructInit = true,
                         bool collectDefine = true,
                         bool collectVar = true)
      : m_context(context), 
        m_collectEnum(collectEnum),
        m_collectStruct(collectStruct), 
        m_collectFunc(collectFunc),
        m_collectTypedef(collectTypedef),
        m_collectStructInit(collectStructInit), 
        m_collectDefine(collectDefine),
        m_collectVar(collectVar) {}

  /**
   * @brief Visit function declarations
   */
  bool VisitFunctionDecl(FunctionDecl *funcDecl) {
    if (!m_collectFunc) return true;
    
    if (funcDecl->isThisDeclarationADefinition()) {
      std::string funcName = funcDecl->getNameAsString();
      if (!funcName.empty()) {
        output_decl(funcDecl, "func.jsonl");
      }
    }
    return true;
  }

  /**
   * @brief Visit record (struct/union) declarations
   */
  bool VisitRecordDecl(RecordDecl *recordDecl) {
    if (m_collectStruct && recordDecl->isThisDeclarationADefinition()) {
      std::string structName = recordDecl->getNameAsString();
      if (!structName.empty()) {
        output_decl(recordDecl, "struct.jsonl");
      }
    }
    return true;
  }

  /**
   * @brief Visit enum declarations
   */
  bool VisitEnumDecl(EnumDecl *enumDecl) {
    if (!m_collectEnum) return true;
    
    if (enumDecl->isThisDeclarationADefinition()) {
      std::string enumName = enumDecl->getNameAsString();
      if (!enumName.empty()) {
        output_decl(enumDecl, "enum.jsonl");
      }
    }
    return true;
  }

  /**
   * @brief Visit typedef declarations
   */
  bool VisitTypedefDecl(TypedefDecl *typedefDecl) {
    QualType underlyingType = typedefDecl->getUnderlyingType();
    std::string aliasName = typedefDecl->getNameAsString();
    
    if (aliasName.empty()) return true;
    
    // Handle enum typedefs
    if (m_collectEnum) {
      if (const EnumType *enumType = underlyingType->getAs<EnumType>()) {
        EnumDecl *enumDecl = enumType->getDecl();
        std::string enumName = enumDecl->getNameAsString();
        output_decl(typedefDecl, "enum-typedef.jsonl", true, enumName);
      }
    }
    
    // Handle struct typedefs
    if (m_collectStruct) {
      if (const RecordType *recordType = underlyingType->getAs<RecordType>()) {
        RecordDecl *recordDecl = recordType->getDecl();
        std::string structName = recordDecl->getNameAsString();
        output_decl(typedefDecl, "struct-typedef.jsonl", true, structName);
      }
    }
    
    // Handle regular typedefs
    if (m_collectTypedef) {
      if (const TypedefType *typedefType = underlyingType->getAs<TypedefType>()) {
        TypedefNameDecl *innerTypedefDecl = typedefType->getDecl();
        std::string typedefName = innerTypedefDecl->getNameAsString();
        output_decl(typedefDecl, "typedef.jsonl", true, typedefName);
      }
    }
    
    return true;
  }

  /**
   * @brief Visit variable declarations
   */
  bool VisitVarDecl(VarDecl *varDecl) {
    // Collect file-scope variables
    if (m_collectVar && varDecl->getParentFunctionOrMethod() == nullptr) {
      std::string varName = varDecl->getNameAsString();
      if (!varName.empty()) {
        QualType varType = varDecl->getType();
        std::string typeName = varType.getAsString();
        output_var_decl(varDecl, "var.jsonl", typeName);
      }
    }

    // Collect struct initializations
    if (m_collectStructInit) {
      collectStructInitialization(varDecl);
    }
    
    return true;
  }

private:
  /**
   * @brief Collect struct variable initializations
   */
  void collectStructInitialization(VarDecl *varDecl) {
    // Check if the declaration is in the main file
    if (!m_context->getSourceManager().isInMainFile(varDecl->getBeginLoc())) {
      return;
    }

    if (!varDecl->hasInit()) return;
    
    QualType varType = varDecl->getType();
    if (!varType->isRecordType()) return;
    
    std::string varName = varDecl->getNameAsString();
    if (!varName.empty()) {
      output_decl(varDecl, "struct-init.jsonl");
    }
  }

private:
  ASTContext *m_context;
  bool m_collectEnum;
  bool m_collectStruct;
  bool m_collectFunc;
  bool m_collectTypedef;
  bool m_collectStructInit;
  bool m_collectDefine;
  bool m_collectVar;
};

/**
 * @class StructConsumer
 * @brief AST consumer that manages the visitor and preprocessor callbacks
 */
class StructConsumer : public clang::ASTConsumer {
public:
  explicit StructConsumer(ASTContext *context, 
                          Preprocessor &preprocessor, 
                          bool collectEnum = true,
                          bool collectStruct = true, 
                          bool collectFunc = true,
                          bool collectTypedef = true,
                          bool collectStructInit = true,
                          bool collectDefine = true,
                          bool collectVar = true)
      : m_visitor(context, collectEnum, collectStruct, collectFunc,
                  collectTypedef, collectStructInit, 
                  collectDefine, collectVar),
        m_collectDefine(collectDefine), 
        m_preprocessor(preprocessor), 
        m_context(context) {
    if (m_collectDefine) {
        m_preprocessor.addPPCallbacks(
            std::make_unique<DefineCollector>(m_preprocessor, 
                                             m_collectDefine, 
                                             m_context->getSourceManager()));
    }
  }

  void HandleTranslationUnit(clang::ASTContext &context) override {
    m_visitor.TraverseDecl(context.getTranslationUnitDecl());
  }

private:
  StructVisitor m_visitor;
  bool m_collectDefine;
  Preprocessor &m_preprocessor;
  ASTContext *m_context;
};

/**
 * @class StructAction
 * @brief Frontend action that creates the AST consumer
 */
class StructAction : public clang::ASTFrontendAction {
public:
  std::unique_ptr<clang::ASTConsumer>
  CreateASTConsumer(clang::CompilerInstance &compiler,
                    llvm::StringRef) override {
    return std::make_unique<StructConsumer>(&compiler.getASTContext(), 
                                            compiler.getPreprocessor(),
                                            true,  // collectEnum
                                            true,  // collectStruct
                                            true,  // collectFunc
                                            true,  // collectTypedef
                                            true,  // collectStructInit
                                            true,  // collectDefine
                                            true); // collectVar
  }
};

/**
 * @brief Main entry point for the analysis tool
 */
int main(int argc, const char **argv) {
  // Setup command line options
  llvm::cl::OptionCategory myToolCategory("my-tool options");
  llvm::cl::opt<std::string> optCompileCommands(
      "p", llvm::cl::desc("Specify path to compile_commands.json"),
      llvm::cl::Required, llvm::cl::cat(myToolCategory));
  llvm::cl::ParseCommandLineOptions(argc, argv);

  // Load compile_commands.json
  std::string errorMessage;
  auto compilationDatabase = JSONCompilationDatabase::loadFromFile(
      optCompileCommands, errorMessage,
      clang::tooling::JSONCommandLineSyntax::AutoDetect);

  if (!compilationDatabase) {
    llvm::errs() << "Error loading compile_commands.json: " << errorMessage
                 << "\n";
    return 1;
  }

  // Extract source files from the loaded database
  std::vector<std::string> sources;
  for (const auto &command : compilationDatabase->getAllCompileCommands()) {
    // Only add .c and .h files
    if (command.Filename.find(".c") == std::string::npos &&
        command.Filename.find(".h") == std::string::npos) {
      continue;
    }
    sources.push_back(command.Filename);
  }

  // Process each source file with multithreading
  std::vector<std::future<void>> futures;
  auto frontendAction = newFrontendActionFactory<StructAction>();

  const int maxThreads = 40;

  Semaphore semaphore(maxThreads);
  
  for (const auto &sourcePath : sources) {
    semaphore.wait(); // Wait for an available slot

    // Launch async task for each source file
    futures.push_back(
        std::async(std::launch::async, 
          [&semaphore, &sourcePath, &compilationDatabase, &frontendAction]() {
            std::cout << "Processing: " << sourcePath << std::endl;

            // Process single source file with ClangTool
            std::vector<std::string> currentSource = {sourcePath};
            ClangTool tool(*compilationDatabase, currentSource);
            tool.run(frontendAction.get());

            semaphore.notify(); // Signal that this thread is done
          }));
  }

  // Wait for all tasks to complete
  for (auto &future : futures) {
    future.wait();
  }
  
  return 0;
}
