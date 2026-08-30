#[path = "../src/ports/codex.rs"]
mod codex;

#[test]
fn codex_adapter_exports_bounded_collector() {
    let _ = codex::MAX_LINE_BYTES;
}
