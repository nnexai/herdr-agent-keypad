//! Production process entrypoint.
//!
//! The bundled executable deliberately does not own a service wrapper, shell
//! lifecycle, or HID authority. Herdr launches this process and supplies the
//! socket path; the same `Coordinator` API is exercised by the tracer test.

use herdr_keypad_native::{bounded_channels, BridgeError, BridgeEvent, Coordinator, HerdrRequest};
use tokio::sync::mpsc;

const DEFAULT_HERDR_SOCKET: &str = "/home/nnex/.config/herdr/herdr.sock";

#[tokio::main]
async fn main() -> Result<(), BridgeError> {
    let socket_path = std::env::var_os("HERDR_SOCKET")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| std::path::PathBuf::from(DEFAULT_HERDR_SOCKET));
    let (herdr_tx, herdr_rx, _device_tx, device_rx, effects_tx, mut effects_rx) = bounded_channels();

    // Keep the effect boundary alive while platform adapters are installed by the
    // integration plan. No fixed-rate timer or host keyboard operation is added.
    let _effect_sink = tokio::spawn(async move {
        while effects_rx.recv().await.is_some() {}
    });
    let coordinator = Coordinator::new(HerdrRequest::unix_socket(socket_path), herdr_rx, device_rx, effects_tx)?;
    notify_start(herdr_tx).await?;
    coordinator.run().await
}

async fn notify_start(sender: mpsc::Sender<BridgeEvent>) -> Result<(), BridgeError> {
    sender
        .send(BridgeEvent::HerdrInvalidated)
        .await
        .map_err(|_| BridgeError::channel("Herdr event channel closed"))
}
