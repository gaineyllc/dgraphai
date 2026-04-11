// Package classify provides local file classification before upload.
// This runs entirely on-prem — no file content leaves the machine.
package classify

import "strings"

// ClassifyFile returns (mime_type, file_category) for a given file extension.
// These are best-effort classifications based on extension alone.
// The Rust enricher (if available) provides deeper content-based classification.
func ClassifyFile(ext string) (mimeType, fileCategory string) {
	ext = strings.ToLower(ext)

	switch ext {
	// ── Video ────────────────────────────────────────────────────────
	case ".mkv":
		return "video/x-matroska", "video"
	case ".mp4", ".m4v":
		return "video/mp4", "video"
	case ".avi":
		return "video/x-msvideo", "video"
	case ".mov":
		return "video/quicktime", "video"
	case ".wmv":
		return "video/x-ms-wmv", "video"
	case ".flv":
		return "video/x-flv", "video"
	case ".webm":
		return "video/webm", "video"
	case ".mts", ".m2ts":
		return "video/mp2t", "video"
	case ".mpeg", ".mpg":
		return "video/mpeg", "video"

	// ── Audio ────────────────────────────────────────────────────────
	case ".mp3":
		return "audio/mpeg", "audio"
	case ".flac":
		return "audio/flac", "audio"
	case ".aac":
		return "audio/aac", "audio"
	case ".wav":
		return "audio/wav", "audio"
	case ".ogg":
		return "audio/ogg", "audio"
	case ".m4a":
		return "audio/mp4", "audio"
	case ".opus":
		return "audio/opus", "audio"
	case ".wma":
		return "audio/x-ms-wma", "audio"

	// ── Images ───────────────────────────────────────────────────────
	case ".jpg", ".jpeg":
		return "image/jpeg", "image"
	case ".png":
		return "image/png", "image"
	case ".gif":
		return "image/gif", "image"
	case ".webp":
		return "image/webp", "image"
	case ".bmp":
		return "image/bmp", "image"
	case ".tiff", ".tif":
		return "image/tiff", "image"
	case ".svg":
		return "image/svg+xml", "image"
	case ".raw", ".cr2", ".nef", ".arw":
		return "image/raw", "image"
	case ".heic", ".heif":
		return "image/heic", "image"
	case ".ico":
		return "image/x-icon", "image"

	// ── Documents ────────────────────────────────────────────────────
	case ".pdf":
		return "application/pdf", "document"
	case ".doc":
		return "application/msword", "document"
	case ".docx":
		return "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "document"
	case ".xls":
		return "application/vnd.ms-excel", "document"
	case ".xlsx":
		return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "document"
	case ".ppt":
		return "application/vnd.ms-powerpoint", "document"
	case ".pptx":
		return "application/vnd.openxmlformats-officedocument.presentationml.presentation", "document"
	case ".odt":
		return "application/vnd.oasis.opendocument.text", "document"
	case ".rtf":
		return "application/rtf", "document"
	case ".pages":
		return "application/x-iwork-pages-sffpages", "document"
	case ".numbers":
		return "application/x-iwork-numbers-sffnumbers", "document"
	case ".keynote":
		return "application/x-iwork-keynote-sffkey", "document"

	// ── Text / Markup ─────────────────────────────────────────────────
	case ".txt":
		return "text/plain", "text"
	case ".md", ".markdown":
		return "text/markdown", "text"
	case ".rst":
		return "text/x-rst", "text"
	case ".csv":
		return "text/csv", "text"
	case ".tsv":
		return "text/tab-separated-values", "text"
	case ".html", ".htm":
		return "text/html", "text"
	case ".xml":
		return "text/xml", "text"
	case ".json":
		return "application/json", "text"
	case ".yaml", ".yml":
		return "application/yaml", "text"
	case ".toml":
		return "application/toml", "text"
	case ".ini", ".cfg", ".conf":
		return "text/plain", "config"
	case ".env":
		return "text/plain", "config"
	case ".log":
		return "text/plain", "log"

	// ── Code ─────────────────────────────────────────────────────────
	case ".go":
		return "text/x-go", "code"
	case ".py":
		return "text/x-python", "code"
	case ".js", ".mjs", ".cjs":
		return "application/javascript", "code"
	case ".tsx":
		return "application/typescript", "code"
	case ".ts":
		return "application/typescript", "code"
	case ".jsx":
		return "text/jsx", "code"
	case ".rs":
		return "text/x-rust", "code"
	case ".c":
		return "text/x-c", "code"
	case ".cpp", ".cc", ".cxx":
		return "text/x-c++", "code"
	case ".h", ".hpp":
		return "text/x-c", "code"
	case ".java":
		return "text/x-java", "code"
	case ".kt", ".kts":
		return "text/x-kotlin", "code"
	case ".swift":
		return "text/x-swift", "code"
	case ".rb":
		return "text/x-ruby", "code"
	case ".php":
		return "text/x-php", "code"
	case ".sh", ".bash", ".zsh":
		return "text/x-shellscript", "code"
	case ".ps1", ".psm1":
		return "text/x-powershell", "code"
	case ".sql":
		return "application/sql", "code"
	case ".cs":
		return "text/x-csharp", "code"
	case ".r":
		return "text/x-r", "code"
	case ".scala":
		return "text/x-scala", "code"
	case ".lua":
		return "text/x-lua", "code"
	case ".dart":
		return "text/x-dart", "code"
	case ".vue":
		return "text/x-vue", "code"
	case ".css", ".scss", ".sass", ".less":
		return "text/css", "code"
	case ".proto":
		return "text/x-protobuf", "code"
	case ".tf", ".tfvars":
		return "text/x-terraform", "code"
	case ".dockerfile":
		return "text/x-dockerfile", "code"
	case ".makefile":
		return "text/x-makefile", "code"

	// ── Archives ─────────────────────────────────────────────────────
	case ".zip":
		return "application/zip", "archive"
	case ".tar":
		return "application/x-tar", "archive"
	case ".gz", ".tgz":
		return "application/gzip", "archive"
	case ".bz2":
		return "application/x-bzip2", "archive"
	case ".xz":
		return "application/x-xz", "archive"
	case ".7z":
		return "application/x-7z-compressed", "archive"
	case ".rar":
		return "application/x-rar-compressed", "archive"
	case ".iso":
		return "application/x-iso9660-image", "archive"

	// ── Executables / Binaries ────────────────────────────────────────
	case ".exe", ".msi":
		return "application/x-msdownload", "executable"
	case ".dll":
		return "application/x-msdownload", "executable"
	case ".so":
		return "application/x-sharedlib", "executable"
	case ".dylib":
		return "application/x-mach-binary", "executable"
	case ".bin":
		return "application/octet-stream", "executable"
	case ".apk":
		return "application/vnd.android.package-archive", "executable"
	case ".deb":
		return "application/x-debian-package", "executable"
	case ".rpm":
		return "application/x-rpm", "executable"
	case ".pkg":
		return "application/x-newton-compatible-pkg", "executable"
	case ".dmg":
		return "application/x-apple-diskimage", "executable"

	// ── Fonts ─────────────────────────────────────────────────────────
	case ".ttf":
		return "font/ttf", "font"
	case ".otf":
		return "font/otf", "font"
	case ".woff":
		return "font/woff", "font"
	case ".woff2":
		return "font/woff2", "font"

	// ── Data ──────────────────────────────────────────────────────────
	case ".db", ".sqlite", ".sqlite3":
		return "application/x-sqlite3", "database"
	case ".parquet":
		return "application/x-parquet", "data"
	case ".avro":
		return "application/avro", "data"
	case ".ndjson", ".jsonl":
		return "application/x-ndjson", "data"

	default:
		return "application/octet-stream", "unknown"
	}
}

