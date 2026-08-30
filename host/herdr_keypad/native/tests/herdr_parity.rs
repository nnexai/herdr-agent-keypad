#[path = "../src/ports/herdr.rs"]
mod herdr;

#[test]
fn herdr_adapter_exports_bounded_client_and_stream() {
    let _ = herdr::MAX_LINE_BYTES;
    let _ = herdr::HerdrClient::new;
}
