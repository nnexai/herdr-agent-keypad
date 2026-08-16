#pragma once

#include <cstddef>
#include <cstdint>

namespace phase1::protocol {

constexpr std::size_t kMaxLineBytes = 4096;
constexpr std::size_t kMaxIdentifierBytes = 64;
constexpr std::size_t kMaxPayloadStringBytes = 128;
constexpr std::size_t kRecentSequenceCapacity = 16;
constexpr std::size_t kQueueCapacity = 16;

// Keep this enum and rejection_name() in one module so host golden vectors can
// name every failure before any caller-specific dispatch occurs.
enum class RejectReason : uint8_t {
  Ok = 0,
  EmptyLine,
  MissingLf,
  LineTooLong,
  InvalidUtf8,
  InvalidJson,
  UnknownField,
  InvalidVersion,
  UnknownType,
  InvalidEnvelope,
  InvalidPayload,
  InvalidShape,
  InvalidIdentifier,
  InvalidSequence,
  InvalidReplyTo,
  InvalidDigest,
  DigestMismatch,
  BootMismatch,
  SessionMismatch,
  OutOfOrder,
  Duplicate,
  QueueFull,
};

const char* rejection_name(RejectReason reason);

struct Frame {
  uint8_t version = 0;
  char type[16] = {};
  char boot_id[kMaxIdentifierBytes + 1] = {};
  char session_id[kMaxIdentifierBytes + 1] = {};
  uint32_t sequence = 0;
  uint32_t reply_to = 0;
  bool has_reply_to = false;
  char digest[17] = {};
  char payload_text[kMaxLineBytes + 1] = {};
  std::size_t payload_length = 0;
};

struct Result {
  bool accepted = false;
  bool dispatched = false;
  bool session_transition = false;
  RejectReason reason = RejectReason::InvalidJson;
  Frame frame{};
};

class FrameCodec final {
 public:
  static Result decode(const uint8_t* line, std::size_t length);
  static bool encode(const Frame& frame, const char* payload_json, std::size_t payload_length,
                     char* output, std::size_t output_capacity, std::size_t& output_length);
  static uint64_t digest_payload(const char* payload_json, std::size_t payload_length);
  static void format_digest(uint64_t digest, char output[17]);
};

class ProtocolSession final {
 public:
  ProtocolSession(const char* boot_id = "", const char* session_id = "",
                  std::size_t queue_capacity = kQueueCapacity);

  void reset(const char* boot_id, const char* session_id);
  void prime_received(uint32_t sequence);
  Result accept(const uint8_t* line, std::size_t length, bool dispatch = true);
  bool complete();
  std::size_t discard_pending();
  std::size_t pending_count() const { return pending_count_; }
  uint32_t last_received_sequence() const { return last_received_sequence_; }
  bool active() const { return session_id_[0] != '\0'; }
  const char* boot_id() const { return boot_id_; }
  const char* session_id() const { return session_id_; }

 private:
  bool seen(uint32_t sequence) const;
  void remember(uint32_t sequence);

  char boot_id_[kMaxIdentifierBytes + 1] = {};
  char session_id_[kMaxIdentifierBytes + 1] = {};
  uint32_t last_received_sequence_ = 0;
  uint32_t recent_[kRecentSequenceCapacity] = {};
  std::size_t recent_count_ = 0;
  std::size_t recent_cursor_ = 0;
  std::size_t pending_count_ = 0;
  std::size_t queue_capacity_ = kQueueCapacity;
};


}  // namespace phase1::protocol
