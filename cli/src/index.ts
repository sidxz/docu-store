import { Command } from "commander";
import { loginCommand } from "./commands/login.js";
import { logoutCommand } from "./commands/logout.js";
import { whoamiCommand } from "./commands/whoami.js";
import { configSetCommand, configShowCommand } from "./commands/config.js";
import { uploadCommand } from "./commands/upload.js";
import { listCommand } from "./commands/list.js";
import { searchCommand } from "./commands/search.js";
import { statusCommand } from "./commands/status.js";
import { summaryCommand } from "./commands/summary.js";
import { exportCommand } from "./commands/export.js";
import { deleteCommand } from "./commands/delete.js";
import {
  chatCommand,
  chatListCommand,
  chatShowCommand,
  chatDeleteCommand,
} from "./commands/chat.js";
import { dashboardCommand } from "./commands/dashboard.js";
import {
  tagsPopularCommand,
  tagsSuggestCommand,
  tagsCategoriesCommand,
} from "./commands/tags.js";
import { compoundsSearchCommand } from "./commands/compounds.js";
import {
  adminWorkflowsCommand,
  adminPipelineCommand,
  adminVectorsCommand,
  adminTokensCommand,
} from "./commands/admin.js";
import { reprocessCommand } from "./commands/reprocess.js";

declare const __CLI_VERSION__: string;

const program = new Command();

program
  .name("docu")
  .description("CLI client for docu-store — manage and search documents")
  .version(__CLI_VERSION__)
  .addHelpText("after", `
Examples:
  $ docu login                              Authenticate via OAuth
  $ docu upload ./papers --recursive        Upload a directory of PDFs
  $ docu search "kinase inhibitor"          Semantic search
  $ docu chat "What compounds target EGFR?" One-shot RAG chat
  $ docu chat -i                            Interactive chat REPL
  $ docu compounds search "CC(=O)Oc1ccccc1C(=O)O"
  $ docu dashboard                          Workspace overview
  $ docu status                             Processing status

Run docu <command> --help for details on any command.
`);

// ── Login ──────────────────────────────────────────────────────────

program
  .command("login")
  .description("Authenticate via browser OAuth")
  .option("-p, --provider <provider>", "Identity provider (github, google)", "github")
  .option("-w, --workspace <workspace>", "Workspace slug or ID")
  .option("-t, --token <token>", "Paste an authz token directly (headless fallback)")
  .option("--sentinel-url <url>", "Override Sentinel URL")
  .action(loginCommand);

// ── Logout ─────────────────────────────────────────────────────────

program
  .command("logout")
  .description("Clear stored credentials")
  .action(logoutCommand);

// ── Whoami ─────────────────────────────────────────────────────────

program
  .command("whoami")
  .description("Show current user and workspace")
  .action(whoamiCommand);

// ── Config ─────────────────────────────────────────────────────────

const configCmd = program
  .command("config")
  .description("Manage CLI configuration");

configCmd
  .command("set <key> <value>")
  .description("Set a config value (sentinel-url, api-url)")
  .action(configSetCommand);

configCmd
  .command("show")
  .description("Show current configuration")
  .action(configShowCommand);

// ── Upload ─────────────────────────────────────────────────────────

program
  .command("upload <path>")
  .description("Upload a file or directory to docu-store")
  .option("-r, --recursive", "Scan subdirectories recursively")
  .option("--resume", "Skip files already uploaded (match by filename)")
  .option("--dry-run", "List files without uploading")
  .option("--type <type>", "Artifact type", "RESEARCH_ARTICLE")
  .option("--visibility <visibility>", "Visibility (workspace, private)", "workspace")
  .option("--delay <seconds>", "Delay between uploads in seconds", "2")
  .option("--glob <pattern>", "File glob pattern (default: *.pdf)")
  .option("--api-url <url>", "Override API URL")
  .action(uploadCommand);

// ── List ──────────────────────────────────────────────────────────

program
  .command("list")
  .alias("ls")
  .description("List documents in the workspace")
  .option("-l, --limit <n>", "Number of documents to show", "20")
  .option("-s, --sort <field>", "Sort by (date, name)", "date")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(listCommand);

// ── Search ────────────────────────────────────────────────────────

program
  .command("search <query>")
  .description("Search documents by text or semantic similarity")
  .option("-l, --limit <n>", "Max results", "5")
  .option("-t, --type <type>", "Result type (all, summary)", "all")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(searchCommand);

// ── Status ────────────────────────────────────────────────────────

program
  .command("status [filename]")
  .description("Show processing status of documents")
  .option("--id <artifact-id>", "Look up by artifact ID instead of filename")
  .option("-l, --limit <n>", "Number of recent documents (when no filename)", "10")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(statusCommand);

// ── Summary ───────────────────────────────────────────────────────

program
  .command("summary <filename>")
  .description("Show AI-generated summary of a document")
  .option("--id <artifact-id>", "Look up by artifact ID instead of filename")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(summaryCommand);

// ── Export ─────────────────────────────────────────────────────────

program
  .command("export <filename>")
  .description("Download the original document")
  .option("--id <artifact-id>", "Look up by artifact ID instead of filename")
  .option("-o, --out <dir>", "Output directory (default: current directory)")
  .option("--api-url <url>", "Override API URL")
  .action(exportCommand);

// ── Delete ────────────────────────────────────────────────────────

program
  .command("delete <filename>")
  .alias("rm")
  .description("Delete a document")
  .option("--id <artifact-id>", "Look up by artifact ID instead of filename")
  .option("-f, --force", "Skip confirmation prompt")
  .option("--api-url <url>", "Override API URL")
  .action(deleteCommand);

// ── Chat ──────────────────────────────────────────────────────────

const chatCmd = program
  .command("chat [message]")
  .description("Chat with your documents (RAG)")
  .option("-i, --interactive", "Interactive REPL mode")
  .option("--mode <mode>", "Pipeline mode (quick, thinking, deep_thinking)")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .addHelpText("after", `
Examples:
  $ docu chat "What is the mechanism of action of aspirin?"
  $ docu chat -i                            Interactive REPL
  $ docu chat -i --mode thinking            Use thinking mode
  $ docu chat list                          List conversations
  $ docu chat show <id>                     Show conversation
`)
  .action(chatCommand);

chatCmd
  .command("list")
  .description("List past conversations")
  .option("-l, --limit <n>", "Number of conversations", "20")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(chatListCommand);

chatCmd
  .command("show <conversation-id>")
  .description("Show conversation with messages")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(chatShowCommand);

chatCmd
  .command("delete <conversation-id>")
  .description("Delete a conversation")
  .option("-f, --force", "Skip confirmation prompt")
  .option("--api-url <url>", "Override API URL")
  .action(chatDeleteCommand);

// ── Dashboard ─────────────────────────────────────────────────────

program
  .command("dashboard")
  .description("Show workspace statistics")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(dashboardCommand);

// ── Tags ──────────────────────────────────────────────────────────

const tagsCmd = program
  .command("tags")
  .description("Browse tags and categories");

tagsCmd
  .command("popular")
  .description("Show most popular tags")
  .option("-l, --limit <n>", "Number of tags", "10")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(tagsPopularCommand);

tagsCmd
  .command("suggest <query>")
  .description("Autocomplete tag suggestions")
  .option("-l, --limit <n>", "Number of suggestions", "10")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(tagsSuggestCommand);

tagsCmd
  .command("categories")
  .description("List tag categories with counts")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(tagsCategoriesCommand);

// ── Compounds ─────────────────────────────────────────────────────

const compoundsCmd = program
  .command("compounds")
  .description("Compound structure search");

compoundsCmd
  .command("search <smiles>")
  .description("Search by SMILES structural similarity")
  .option("-l, --limit <n>", "Max results", "10")
  .option("--threshold <score>", "Min similarity score (0-1)", "0.7")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(compoundsSearchCommand);

// ── Admin ─────────────────────────────────────────────────────────

const adminCmd = program
  .command("admin")
  .description("Admin statistics (requires admin access)");

adminCmd
  .command("workflows")
  .description("Show Temporal workflow statistics")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(adminWorkflowsCommand);

adminCmd
  .command("pipeline")
  .description("Show document pipeline statistics")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(adminPipelineCommand);

adminCmd
  .command("vectors")
  .description("Show vector store statistics")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(adminVectorsCommand);

adminCmd
  .command("tokens")
  .description("Show token usage statistics")
  .option("--period <period>", "Aggregation period (day, week, month)", "week")
  .option("--json", "Output as JSON")
  .option("--api-url <url>", "Override API URL")
  .action(adminTokensCommand);

// ── Reprocess ─────────────────────────────────────────────────────

program
  .command("reprocess <filename>")
  .description("Re-trigger document processing workflows")
  .option("--id <artifact-id>", "Look up by artifact ID instead of filename")
  .option("--summarize", "Trigger summarization only")
  .option("--metadata", "Trigger metadata extraction only")
  .option("--all", "Trigger all workflows")
  .option("--api-url <url>", "Override API URL")
  .action(reprocessCommand);

program.parse();
