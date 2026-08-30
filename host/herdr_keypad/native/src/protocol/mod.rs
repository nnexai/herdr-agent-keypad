//! Closed device protocol modules.

pub mod v2;

pub use v2::{AgentSnapshot, FocusIntentPayload, FocusResultPayload, FrameType, Payload, ProtocolFrame, ProtocolSession};
