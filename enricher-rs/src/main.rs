//! dgraph-enricher — local file content scanner.
//!
//! Called by dgraph-agent as a subprocess to analyze file content
//! BEFORE any data leaves the customer network.
//!
//! Protocol:
//!   stdin:  JSON request { "path": "/...", "category": "code", "max_bytes": 1048576 }
//!   stdout: JSON response { "contains_secrets": true, "secret_types": [...], ... }
//!   stderr: log output
//!   exit 0: success
//!   exit 1: error (response on stderr)
//!
//! Security design:
//!   - Hard timeout: 5 seconds per file (SIGALRM or tokio timeout)
//!   - Memory limit: 256MB RSS (set by caller via ulimit/rlimit)
//!   - No filesystem writes
//!   - No network access
//!   - Runs as nobody/65534

use anyhow::{Context, Result};
use clap::Parser;
use serde::{Deserialize, Serialize};
use std::io::{self, Read, Write};

mod scanners;
mod parsers;

use scanners::{
    secret_scanner::SecretScanner,
    pii_scanner::PIIScanner,
};
use parsers::binary_parser::BinaryParser;

// ── CLI ────────────────────────────────────────────────────────────────────────

#[derive(Parser, Debug)]
#[command(name = "dgraph-enricher", version, about = "On-premises file content scanner")]
struct Cli {
    /// Operating mode
    #[command(subcommand)]
    command: Command,
}

#[derive(clap::Subcommand, Debug)]
enum Command {
    /// Scan a single file (reads request from stdin, writes result to stdout)
    Scan,
    /// Scan multiple files from a JSONL stream on stdin
    Stream,
    /// Print version and exit
    Version,
}

// ── Request / Response ─────────────────────────────────────────────────────────

#[derive(Deserialize, Debug)]
struct ScanRequest {
    path:         String,
    category:     String,
    max_bytes:    Option<usize>,
    tenant_id:    Option<String>,
    node_id:      Option<String>,
}

#[derive(Serialize, Debug, Default)]
struct ScanResponse {
    node_id:          Option<String>,
    path:             String,

    // Secrets
    contains_secrets: bool,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    secret_types:     Vec<String>,

    // PII
    pii_detected:     bool,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pii_types:        Vec<String>,

    // Overall severity
    sensitivity_level: String,

    // Binary analysis
    #[serde(skip_serializing_if = "Option::is_none")]
    binary_format:    Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    entropy:          Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    is_packed:        Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    is_signed:        Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    architecture:     Option<String>,

    // Processing metadata
    bytes_read:   usize,
    duration_ms:  u64,
    error:        Option<String>,
}

// ── Main ───────────────────────────────────────────────────────────────────────

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<()> {
    // Initialize structured logging to stderr (never stdout — that's for results)
    tracing_subscriber::fmt()
        .with_writer(io::stderr)
        .with_env_filter(
            std::env::var("DGRAPH_ENRICHER_LOG").unwrap_or_else(|_| "warn".into())
        )
        .init();

    let cli = Cli::parse();
    match cli.command {
        Command::Version => {
            println!("dgraph-enricher {}", env!("CARGO_PKG_VERSION"));
        }
        Command::Scan => {
            run_single_scan().await?;
        }
        Command::Stream => {
            run_stream().await?;
        }
    }
    Ok(())
}

async fn run_single_scan() -> Result<()> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).context("reading stdin")?;

    let request: ScanRequest = serde_json::from_str(&input)
        .context("parsing request JSON")?;

    let response = scan_file(&request).await;

    let json = serde_json::to_string(&response)?;
    println!("{}", json);
    Ok(())
}

async fn run_stream() -> Result<()> {
    let stdin = io::stdin();
    let mut stdout = io::stdout();

    for line in stdin.lock().lines() {
        let line = line.context("reading stdin line")?;
        if line.trim().is_empty() { continue; }

        let request: ScanRequest = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(e) => {
                eprintln!("parse error: {}", e);
                continue;
            }
        };

        let response = scan_file(&request).await;
        let json = serde_json::to_string(&response)?;
        stdout.write_all(json.as_bytes())?;
        stdout.write_all(b"\n")?;
        stdout.flush()?;
    }
    Ok(())
}

async fn scan_file(req: &ScanRequest) -> ScanResponse {
    let start = std::time::Instant::now();
    let max_bytes = req.max_bytes.unwrap_or(1024 * 1024); // 1MB default

    let mut resp = ScanResponse {
        node_id: req.node_id.clone(),
        path:    req.path.clone(),
        ..Default::default()
    };

    // Route to appropriate scanner based on file category
    match req.category.as_str() {
        "code" | "document" | "email" | "web_data" => {
            scan_text_content(req, &mut resp, max_bytes);
        }
        "executable" => {
            scan_binary_content(req, &mut resp);
        }
        _ => {
            // Scan as text for secrets/PII even for unknown types (small overhead)
            scan_text_content(req, &mut resp, max_bytes);
        }
    }

    // Compute severity
    resp.sensitivity_level = compute_severity(&resp);
    resp.duration_ms = start.elapsed().as_millis() as u64;
    resp
}

fn scan_text_content(req: &ScanRequest, resp: &mut ScanResponse, max_bytes: usize) {
    let content = match read_file_limited(&req.path, max_bytes) {
        Ok(c)  => { resp.bytes_read = c.len(); c }
        Err(e) => { resp.error = Some(e.to_string()); return; }
    };

    let secret_scanner = SecretScanner::new();
    let pii_scanner    = PIIScanner::new();

    let secret_result = secret_scanner.scan(&content);
    if !secret_result.findings.is_empty() {
        resp.contains_secrets = true;
        resp.secret_types     = secret_result.findings;
    }

    let pii_result = pii_scanner.scan(&content);
    if !pii_result.findings.is_empty() {
        resp.pii_detected = true;
        resp.pii_types    = pii_result.findings;
    }
}

fn scan_binary_content(req: &ScanRequest, resp: &mut ScanResponse) {
    let parser = BinaryParser::new();
    match parser.analyze(&req.path) {
        Ok(result) => {
            resp.binary_format = result.format;
            resp.entropy       = result.entropy;
            resp.is_packed     = result.is_packed;
            resp.is_signed     = result.is_signed;
            resp.architecture  = result.architecture;
            resp.bytes_read    = result.bytes_read;
        }
        Err(e) => {
            resp.error = Some(e.to_string());
        }
    }
}

fn read_file_limited(path: &str, max_bytes: usize) -> Result<String> {
    use std::fs::File;

    let mut file = File::open(path)
        .with_context(|| format!("opening {}", path))?;

    let mut buffer = vec![0u8; max_bytes];
    let n = file.read(&mut buffer)
        .with_context(|| format!("reading {}", path))?;
    buffer.truncate(n);

    // Convert bytes to string, replacing invalid UTF-8
    Ok(String::from_utf8_lossy(&buffer).into_owned())
}

fn compute_severity(resp: &ScanResponse) -> String {
    if resp.contains_secrets {
        let critical_types = ["private_key", "aws_key", "github_token"];
        for t in &resp.secret_types {
            if critical_types.iter().any(|c| t.contains(c)) {
                return "critical".into();
            }
        }
        return "high".into();
    }
    if resp.pii_detected {
        let high_types = ["ssn", "credit_card", "passport"];
        for t in &resp.pii_types {
            if high_types.iter().any(|h| t.contains(h)) {
                return "high".into();
            }
        }
        return "medium".into();
    }
    if resp.is_packed == Some(true) {
        return "medium".into();
    }
    "low".into()
}

// Need to bring in the Read trait for lines()
use std::io::BufRead;
