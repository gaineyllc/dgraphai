//! Binary format parser — PE/ELF/Mach-O analysis.
//! Uses the `object` crate for safe parsing of untrusted binary content.
//! Detects packing (high entropy), signing, and architecture.

use anyhow::{Context, Result};
use object::{Object, ObjectSection};
use std::fs;

pub struct BinaryAnalysis {
    pub format:       Option<String>,
    pub architecture: Option<String>,
    pub is_signed:    Option<bool>,
    pub is_packed:    Option<bool>,
    pub entropy:      Option<f64>,
    pub bytes_read:   usize,
}

pub struct BinaryParser;

impl BinaryParser {
    pub fn new() -> Self { Self }

    pub fn analyze(&self, path: &str) -> Result<BinaryAnalysis> {
        let data = fs::read(path)
            .with_context(|| format!("reading binary {}", path))?;

        let bytes_read = data.len();
        let entropy    = shannon_entropy(&data);
        let is_packed  = entropy > 7.2; // High entropy = likely packed/encrypted

        // Parse format using `object` crate — memory-safe even on malformed input
        let (format, architecture, is_signed) = match object::File::parse(&*data) {
            Ok(file) => {
                let fmt   = format_name(&file);
                let arch  = arch_name(&file);
                let signed = detect_signature(&file);
                (Some(fmt), Some(arch), Some(signed))
            }
            Err(_) => {
                // Unknown or malformed binary — still report entropy
                (detect_magic(&data), None, None)
            }
        };

        Ok(BinaryAnalysis {
            format,
            architecture,
            is_signed,
            is_packed: Some(is_packed),
            entropy: Some(entropy),
            bytes_read,
        })
    }
}

/// Shannon entropy of a byte sequence. Range: 0.0 (uniform) to 8.0 (random).
/// Values > 7.2 suggest packed, encrypted, or compressed content.
pub fn shannon_entropy(data: &[u8]) -> f64 {
    if data.is_empty() { return 0.0; }

    let mut freq = [0u64; 256];
    for &byte in data {
        freq[byte as usize] += 1;
    }

    let len = data.len() as f64;
    freq.iter()
        .filter(|&&c| c > 0)
        .map(|&c| {
            let p = c as f64 / len;
            -p * p.log2()
        })
        .sum()
}

fn format_name(file: &object::File) -> String {
    use object::BinaryFormat::*;
    match file.format() {
        Pe     => "PE".into(),
        Elf    => "ELF".into(),
        MachO  => "MACHO".into(),
        Wasm   => "WASM".into(),
        Coff   => "COFF".into(),
        Xcoff  => "XCOFF".into(),
        _      => "Unknown".into(),
    }
}

fn arch_name(file: &object::File) -> String {
    use object::Architecture::*;
    match file.architecture() {
        X86_64  => "x86_64".into(),
        X86     => "x86".into(),
        Aarch64 => "arm64".into(),
        Arm     => "arm".into(),
        Riscv64 => "riscv64".into(),
        _       => "unknown".into(),
    }
}

fn detect_signature(file: &object::File) -> bool {
    // PE: check for Authenticode signature (IMAGE_DIRECTORY_ENTRY_SECURITY)
    // ELF: check for GPG-signed sections
    // Mach-O: check for code signature section
    // Simplified heuristic: look for signature-related sections
    for section in file.sections() {
        if let Ok(name) = section.name() {
            let lower = name.to_lowercase();
            if lower.contains("signature") || lower.contains("codesign") || lower == ".reloc" {
                return true;
            }
        }
    }
    false
}

fn detect_magic(data: &[u8]) -> Option<String> {
    if data.len() < 4 { return None; }
    match &data[..4] {
        b"MZ\x90\x00" | b"MZ"    => Some("PE".into()),
        [0x7f, b'E', b'L', b'F'] => Some("ELF".into()),
        [0xCF, 0xFA, 0xED, 0xFE] |
        [0xCE, 0xFA, 0xED, 0xFE] => Some("MACHO".into()),
        b"\x00asm"               => Some("WASM".into()),
        _                        => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn entropy_empty() {
        assert_eq!(shannon_entropy(&[]), 0.0);
    }

    #[test]
    fn entropy_uniform_bytes() {
        let data: Vec<u8> = vec![0xAA; 1024];
        assert_eq!(shannon_entropy(&data), 0.0);
    }

    #[test]
    fn entropy_all_256_bytes() {
        let data: Vec<u8> = (0..=255u8).collect();
        let e = shannon_entropy(&data);
        // Perfect uniform distribution = 8.0
        assert!((e - 8.0).abs() < 0.001, "expected ~8.0, got {}", e);
    }

    #[test]
    fn entropy_high_for_random_data() {
        // Pseudo-random data has high entropy
        let data: Vec<u8> = (0..1024).map(|i| ((i * 37 + 13) % 256) as u8).collect();
        let e = shannon_entropy(&data);
        assert!(e > 6.0, "expected high entropy, got {}", e);
    }

    #[test]
    fn entropy_low_for_text() {
        let data = b"AAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBB";
        let e = shannon_entropy(data);
        assert!(e < 4.0, "expected low entropy for repetitive text, got {}", e);
    }

    #[test]
    fn packed_threshold_correct() {
        // 7.2 threshold
        let random: Vec<u8> = (0..256).map(|i| i as u8).collect();
        let e = shannon_entropy(&random);
        let is_packed = e > 7.2;
        // 256 unique bytes in 256-byte buffer = entropy 8.0, should be "packed"
        assert!(is_packed);
    }

    #[test]
    fn detect_magic_elf() {
        let elf_magic = [0x7f, b'E', b'L', b'F', 0, 0, 0, 0];
        assert_eq!(detect_magic(&elf_magic), Some("ELF".into()));
    }

    #[test]
    fn detect_magic_pe() {
        let pe_magic = b"MZ\x90\x00rest";
        assert_eq!(detect_magic(pe_magic), Some("PE".into()));
    }

    #[test]
    fn detect_magic_unknown() {
        assert_eq!(detect_magic(b"????"), None);
    }
}
