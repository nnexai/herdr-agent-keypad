#include "protocol.h"

#include <cstdio>
#include <cstring>

namespace phase1::protocol {
namespace {

constexpr std::size_t kMaxJsonNesting = 8;
struct Cursor {
  const char* p;
  const char* end;
  bool depth_exceeded = false;

  void ws() {
    while (p < end && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) ++p;
  }

  bool take(char value) {
    ws();
    if (p >= end || *p != value) return false;
    ++p;
    return true;
  }

  bool string(char* output, std::size_t capacity) {
    ws();
    if (p >= end || *p != '"' || capacity == 0) return false;
    ++p;
    std::size_t used = 0;
    while (p < end && *p != '"') {
      unsigned char byte = static_cast<unsigned char>(*p++);
      if (byte < 0x20 || byte >= 0x80) return false;
      if (byte == '\\') {
        if (p >= end) return false;
        const char escaped = *p++;
        if (escaped == 'u') return false;  // v1 fixture strings are ASCII.
        if (escaped == '"' || escaped == '\\' || escaped == '/') {
          byte = static_cast<unsigned char>(escaped);
        } else if (escaped == 'b' || escaped == 'f' || escaped == 'n' || escaped == 'r' || escaped == 't') {
          return false;  // no control characters in bounded protocol strings.
        } else {
          return false;
        }
      }
      if (used + 1 >= capacity) return false;
      output[used++] = static_cast<char>(byte);
    }
    if (p >= end || *p != '"') return false;
    ++p;
    output[used] = '\0';
    return true;
  }

  bool uint32(uint32_t& output) {
    ws();
    if (p >= end || *p < '0' || *p > '9') return false;
    uint64_t value = 0;
    while (p < end && *p >= '0' && *p <= '9') {
      value = value * 10U + static_cast<unsigned>(*p++ - '0');
      if (value > 0xffffffffULL) return false;
    }
    output = static_cast<uint32_t>(value);
    return true;
  }

  bool boolean(bool& output) {
    ws();
    if (end - p >= 4 && std::strncmp(p, "true", 4) == 0) {
      p += 4;
      output = true;
      return true;
    }
    if (end - p >= 5 && std::strncmp(p, "false", 5) == 0) {
      p += 5;
      output = false;
      return true;
    }
    return false;
  }

  bool null_value() {
    ws();
    if (end - p < 4 || std::strncmp(p, "null", 4) != 0) return false;
    p += 4;
    return true;
  }
  bool value(std::size_t depth = 0) {
    ws();
    if (p >= end) return false;
    if (depth > kMaxJsonNesting) {
      depth_exceeded = true;
      return false;
    }
    if (*p == '"') {
      ++p;
      while (p < end) {
        if (*p == '\\') {
          ++p;
          if (p >= end) return false;
          ++p;
        } else if (*p++ == '"') {
          return true;
        }
      }
      return false;
    }
    if (*p == '{') {
      ++p;
      ws();
      if (take('}')) return true;
      while (p < end) {
        char key[32];
        if (!string(key, sizeof(key)) || !take(':') || !value(depth + 1)) return false;
        ws();
        if (take('}')) return true;
        if (!take(',')) return false;
      }
      return false;
    }
    if (*p == '[') {
      ++p;
      ws();
      if (take(']')) return true;
      while (p < end) {
        if (!value(depth + 1)) return false;
        ws();
        if (take(']')) return true;
        if (!take(',')) return false;
      }
      return false;
    }
    bool ignored_bool = false;
    uint32_t ignored_uint = 0;
    return boolean(ignored_bool) || null_value() || uint32(ignored_uint);
  }
};

bool copy_text(char* destination, std::size_t capacity, const char* source, std::size_t length) {
  if (length + 1 > capacity) return false;
  std::memcpy(destination, source, length);
  destination[length] = '\0';
  return true;
}

bool valid_identifier(const char* value) {
  const std::size_t length = std::strlen(value);
  if (length == 0 || length > kMaxIdentifierBytes) return false;
  for (std::size_t index = 0; index < length; ++index) {
    const char c = value[index];
    if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')) return false;
  }
  return true;
}

bool valid_digest(const char* value) {
  if (std::strlen(value) != 16) return false;
  for (std::size_t index = 0; index < 16; ++index) {
    const char c = value[index];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
  }
  return true;
}

bool digest_matches(const char* expected, const char* payload, std::size_t payload_length) {
  char calculated[17];
  FrameCodec::format_digest(FrameCodec::digest_payload(payload, payload_length), calculated);
  return std::strcmp(expected, calculated) == 0;
}

bool payload_value_string(Cursor& cursor, char* destination, std::size_t capacity) {
  return cursor.string(destination, capacity);
}

RejectReason parse_payload(Cursor& cursor, Frame& frame, const char* payload_start) {
  if (!cursor.take('{')) return RejectReason::InvalidPayload;
  uint32_t mask = 0;
  const char* payload_end = nullptr;
  char event_kind[32] = {};
  while (true) {
    cursor.ws();
    if (cursor.take('}')) {
      payload_end = cursor.p;
      break;
    }
    char key[32];
    if (!cursor.string(key, sizeof(key)) || !cursor.take(':')) return RejectReason::InvalidJson;
    uint32_t bit = 0;
    if (std::strcmp(key, "accepted") == 0) bit = 1U << 0;
    else if (std::strcmp(key, "device_id") == 0) bit = 1U << 1;
    else if (std::strcmp(key, "firmware") == 0) bit = 1U << 2;
    else if (std::strcmp(key, "protocol") == 0) bit = 1U << 3;
    else if (std::strcmp(key, "panel") == 0) bit = 1U << 4;
    else if (std::strcmp(key, "step_id") == 0) bit = 1U << 5;
    else if (std::strcmp(key, "stimulus") == 0) bit = 1U << 6;
    else if (std::strcmp(key, "key") == 0) bit = 1U << 7;
    else if (std::strcmp(key, "kind") == 0) bit = 1U << 8;
    else if (std::strcmp(key, "code") == 0) bit = 1U << 9;
    else if (std::strcmp(key, "detail") == 0) bit = 1U << 10;
    else if (std::strcmp(key, "acknowledged") == 0) bit = 1U << 11;
    else if (std::strcmp(key, "digest_mismatch") == 0) bit = 1U << 12;
    else if (std::strcmp(key, "duplicate") == 0) bit = 1U << 13;
    else if (std::strcmp(key, "largest_free_block") == 0) bit = 1U << 14;
    else if (std::strcmp(key, "malformed") == 0) bit = 1U << 15;
    else if (std::strcmp(key, "max_display_flush_us") == 0) bit = 1U << 16;
    else if (std::strcmp(key, "max_key_poll_gap_us") == 0) bit = 1U << 17;
    else if (std::strcmp(key, "minimum_free_heap") == 0) bit = 1U << 18;
    else if (std::strcmp(key, "out_of_order") == 0) bit = 1U << 19;
    else if (std::strcmp(key, "parser_high_water") == 0) bit = 1U << 20;
    else if (std::strcmp(key, "queue_high_water") == 0) bit = 1U << 21;
    else if (std::strcmp(key, "received") == 0) bit = 1U << 22;
    else if (std::strcmp(key, "rejected") == 0) bit = 1U << 23;
    else if (std::strcmp(key, "sent") == 0) bit = 1U << 24;
    else if (std::strcmp(key, "watchdog_reset") == 0) bit = 1U << 25;
    else if (std::strcmp(key, "direction") == 0) bit = 1U << 27;
    else if (std::strcmp(key, "request") == 0) bit = 1U << 26;
    else return RejectReason::InvalidShape;
    if ((mask & bit) != 0) return RejectReason::DuplicateKey;
    mask |= bit;

    if (bit == (1U << 0)) {
      bool value = false;
      if (!cursor.boolean(value)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 1)) {
      char value[kMaxIdentifierBytes + 1];
      if (!payload_value_string(cursor, value, sizeof(value)) || !valid_identifier(value)) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 2)) {
      char value[kMaxPayloadStringBytes + 1];
      if (!payload_value_string(cursor, value, sizeof(value)) || std::strlen(value) == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 3)) {
      uint32_t value = 0;
      if (!cursor.uint32(value) || value != 1) return RejectReason::InvalidShape;
    } else if (bit == (1U << 4)) {
      uint32_t value = 0;
      if (!cursor.uint32(value) || value < 1 || value > 4) return RejectReason::InvalidShape;
    } else if (bit == (1U << 5)) {
      char value[kMaxIdentifierBytes + 1];
      if (!payload_value_string(cursor, value, sizeof(value)) || !valid_identifier(value)) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 6)) {
      char value[kMaxPayloadStringBytes + 1];
      if (!payload_value_string(cursor, value, sizeof(value)) || std::strlen(value) == 0 || std::strlen(value) > 64) return RejectReason::InvalidShape;
    } else if (bit == (1U << 7)) {
      uint32_t value = 0;
      if (!cursor.uint32(value) || value > 4) return RejectReason::InvalidShape;
    } else if (bit == (1U << 8)) {
      if (!payload_value_string(cursor, event_kind, sizeof(event_kind)) ||
          (std::strcmp(event_kind, "key_transition") != 0 && std::strcmp(event_kind, "encoder_transition") != 0)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 9)) {
      char value[kMaxIdentifierBytes + 1];
      if (!payload_value_string(cursor, value, sizeof(value)) || !valid_identifier(value)) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 10)) {
      char value[kMaxPayloadStringBytes + 1];
      if (!payload_value_string(cursor, value, sizeof(value)) || std::strlen(value) == 0 || std::strlen(value) > 128) return RejectReason::InvalidShape;
    } else if (bit == (1U << 27)) {
      char value[kMaxPayloadStringBytes + 1];
      if (!payload_value_string(cursor, value, sizeof(value)) ||
          (std::strcmp(value, "cw") != 0 && std::strcmp(value, "ccw") != 0)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 26)) {
      char value[kMaxPayloadStringBytes + 1];
      if (!payload_value_string(cursor, value, sizeof(value)) ||
          (std::strcmp(value, "proof") != 0 && std::strcmp(value, "reset") != 0)) return RejectReason::InvalidShape;
    } else if (bit >= (1U << 11) && bit <= (1U << 25)) {
      uint32_t value = 0;
      if (!cursor.uint32(value)) return RejectReason::InvalidShape;
    }
    cursor.ws();
    if (cursor.take('}')) {
      payload_end = cursor.p;
      break;
    }
    if (!cursor.take(',')) return RejectReason::InvalidJson;
  }

  const char* type = frame.type;
  uint32_t expected = 0;
  if (std::strcmp(type, "hello") == 0) expected = (1U << 1) | (1U << 2) | (1U << 3);
  else if (std::strcmp(type, "hello_ack") == 0) expected = (1U << 0) | (1U << 1) | (1U << 2) | (1U << 3);
  else if (std::strcmp(type, "probe") == 0) expected = (1U << 4) | (1U << 5) | (1U << 6);
  else if (std::strcmp(type, "probe_ack") == 0) expected = (1U << 0) | (1U << 5);
  else if (std::strcmp(type, "event") == 0) {
    if (std::strcmp(event_kind, "key_transition") == 0) expected = (1U << 7) | (1U << 8) | (1U << 5);
    else if (std::strcmp(event_kind, "encoder_transition") == 0) expected = (1U << 27) | (1U << 8) | (1U << 5);
    else return RejectReason::InvalidShape;
  }
  else if (std::strcmp(type, "error") == 0) expected = (1U << 9) | (1U << 10);
  else if (std::strcmp(type, "metrics") == 0) expected = (1U << 26);
  else if (std::strcmp(type, "metrics_ack") == 0) expected = (1U << 11) | (1U << 12) | (1U << 13) | (1U << 14) | (1U << 15) | (1U << 16) | (1U << 17) | (1U << 18) | (1U << 19) | (1U << 20) | (1U << 21) | (1U << 22) | (1U << 23) | (1U << 24) | (1U << 25);
  else return RejectReason::UnknownType;
  if (mask != expected || payload_end == nullptr) return RejectReason::InvalidShape;
  frame.payload_length = static_cast<std::size_t>(payload_end - payload_start);
  if (!copy_text(frame.payload_text, sizeof(frame.payload_text), payload_start, frame.payload_length)) return RejectReason::LineTooLong;
  return RejectReason::Ok;
}

}  // namespace

const char* rejection_name(RejectReason reason) {
  static const char* names[] = {"ok", "empty_line", "missing_lf", "line_too_long", "invalid_utf8", "invalid_json", "unknown_field", "invalid_version", "unknown_type", "invalid_envelope", "invalid_payload", "invalid_shape", "invalid_identifier", "invalid_sequence", "invalid_reply_to", "invalid_digest", "digest_mismatch", "boot_mismatch", "session_mismatch", "out_of_order", "duplicate", "queue_full", "duplicate_key"};
  const auto index = static_cast<std::size_t>(reason);
  return index < (sizeof(names) / sizeof(names[0])) ? names[index] : "invalid_json";
}

uint64_t FrameCodec::digest_payload(const char* payload_json, std::size_t payload_length) {
  uint64_t digest = 0xcbf29ce484222325ULL;
  for (std::size_t index = 0; index < payload_length; ++index) {
    digest ^= static_cast<unsigned char>(payload_json[index]);
    digest *= 0x100000001b3ULL;
  }
  return digest;
}

void FrameCodec::format_digest(uint64_t digest, char output[17]) {
  std::snprintf(output, 17, "%016llx", static_cast<unsigned long long>(digest));
}

Result FrameCodec::decode(const uint8_t* line, std::size_t length) {
  Result result;
  return decode(line, length, result);
}

Result& FrameCodec::decode(const uint8_t* line, std::size_t length, Result& result) {
  result = Result{};
  result.reason = RejectReason::InvalidJson;
  if (line == nullptr || length == 0) {
    result.reason = RejectReason::EmptyLine;
    return result;
  }
  if (length > kMaxLineBytes) {
    result.reason = RejectReason::LineTooLong;
    return result;
  }
  if (line[length - 1] != '\n') {
    result.reason = RejectReason::MissingLf;
    return result;
  }
  const char* start = reinterpret_cast<const char*>(line);
  Cursor cursor{start, start + length - 1};
  if (!cursor.take('{')) {
    result.reason = RejectReason::InvalidJson;
    return result;
  }
  uint32_t fields = 0;
  while (true) {
    cursor.ws();
    if (cursor.take('}')) break;
    char key[32];
    if (!cursor.string(key, sizeof(key)) || !cursor.take(':')) return result;
    uint32_t bit = 0;
    if (std::strcmp(key, "v") == 0) bit = 1U << 0;
    else if (std::strcmp(key, "type") == 0) bit = 1U << 1;
    else if (std::strcmp(key, "boot_id") == 0) bit = 1U << 2;
    else if (std::strcmp(key, "session_id") == 0) bit = 1U << 3;
    else if (std::strcmp(key, "seq") == 0) bit = 1U << 4;
    else if (std::strcmp(key, "reply_to") == 0) bit = 1U << 5;
    else if (std::strcmp(key, "digest") == 0) bit = 1U << 6;
    else if (std::strcmp(key, "payload") == 0) bit = 1U << 7;
    else {
      result.reason = RejectReason::UnknownField;
      return result;
    }
    if ((fields & bit) != 0) {
      result.reason = RejectReason::DuplicateKey;
      return result;
    }
    fields |= bit;
    if (bit == (1U << 0)) {
      uint32_t value = 0;
      if (!cursor.uint32(value)) {
        result.reason = RejectReason::InvalidVersion;
        return result;
      }
      if (value != 1) {
        result.reason = RejectReason::InvalidVersion;
        return result;
      }
      result.frame.version = static_cast<uint8_t>(value);
    } else if (bit == (1U << 1)) {
      cursor.ws();
      if (cursor.p >= cursor.end || *cursor.p != '"') {
        if (!cursor.value()) result.reason = RejectReason::InvalidJson;
        else result.reason = RejectReason::UnknownType;
        return result;
      }
      if (!cursor.string(result.frame.type, sizeof(result.frame.type))) {
        result.reason = RejectReason::UnknownType;
        return result;
      }
    } else if (bit == (1U << 2)) {
      if (!cursor.string(result.frame.boot_id, sizeof(result.frame.boot_id))) return result;
    } else if (bit == (1U << 3)) {
      if (!cursor.string(result.frame.session_id, sizeof(result.frame.session_id))) return result;
    } else if (bit == (1U << 4)) {
      if (!cursor.uint32(result.frame.sequence) || result.frame.sequence == 0) {
        result.reason = RejectReason::InvalidSequence;
        return result;
      }
    } else if (bit == (1U << 5)) {
      cursor.ws();
      if (cursor.p < cursor.end && *cursor.p == 'n') {
        if (!cursor.null_value()) return result;
        result.frame.has_reply_to = false;
      } else {
        if (!cursor.uint32(result.frame.reply_to) || result.frame.reply_to == 0) {
          result.reason = RejectReason::InvalidReplyTo;
          return result;
        }
        result.frame.has_reply_to = true;
      }
    } else if (bit == (1U << 6)) {
      if (!cursor.string(result.frame.digest, sizeof(result.frame.digest))) return result;
    } else {
      cursor.ws();
      const char* payload_start = cursor.p;
      if (!cursor.value()) {
        result.reason = cursor.depth_exceeded ? RejectReason::InvalidJson : RejectReason::InvalidPayload;
        return result;
      }
      const std::size_t payload_length = static_cast<std::size_t>(cursor.p - payload_start);
      if (!copy_text(result.frame.payload_text, sizeof(result.frame.payload_text), payload_start, payload_length)) {
        result.reason = RejectReason::LineTooLong;
        return result;
      }
      result.frame.payload_length = payload_length;
    }
    cursor.ws();
    if (cursor.take('}')) break;
    if (!cursor.take(',')) return result;
  }
  if (cursor.p != cursor.end) {
    result.reason = RejectReason::InvalidJson;
    return result;
  }
  if (fields != 0xffU) {
    result.reason = RejectReason::InvalidEnvelope;
    return result;
  }
  if (result.frame.version != 1) {
    result.reason = RejectReason::InvalidVersion;
    return result;
  }
  if (std::strcmp(result.frame.type, "hello") != 0 && std::strcmp(result.frame.type, "hello_ack") != 0 && std::strcmp(result.frame.type, "probe") != 0 && std::strcmp(result.frame.type, "probe_ack") != 0 && std::strcmp(result.frame.type, "event") != 0 && std::strcmp(result.frame.type, "error") != 0 && std::strcmp(result.frame.type, "metrics") != 0 && std::strcmp(result.frame.type, "metrics_ack") != 0) {
    result.reason = RejectReason::UnknownType;
    return result;
  }
  {
    Cursor payload_cursor{result.frame.payload_text, result.frame.payload_text + result.frame.payload_length};
    const RejectReason payload_reason = parse_payload(payload_cursor, result.frame, result.frame.payload_text);
    if (payload_reason != RejectReason::Ok) {
      result.reason = payload_reason;
      return result;
    }
  }
  if (!valid_identifier(result.frame.boot_id) || !valid_identifier(result.frame.session_id)) {
    result.reason = RejectReason::InvalidIdentifier;
    return result;
  }
  if (!valid_digest(result.frame.digest)) {
    result.reason = RejectReason::InvalidDigest;
    return result;
  }
  if (!digest_matches(result.frame.digest, result.frame.payload_text, result.frame.payload_length)) {
    result.reason = RejectReason::DigestMismatch;
    return result;
  }
  result.accepted = true;
  result.reason = RejectReason::Ok;
  return result;
}

bool FrameCodec::encode(const Frame& frame, const char* payload_json, std::size_t payload_length,
                        char* output, std::size_t output_capacity, std::size_t& output_length) {
  if (output == nullptr || payload_json == nullptr || output_capacity == 0 ||
      payload_length == 0 || payload_length >= kMaxLineBytes || frame.version != 1 ||
      frame.sequence == 0 || std::strlen(frame.type) == 0 ||
      std::strlen(frame.type) >= sizeof(frame.type) || !valid_identifier(frame.boot_id) ||
      !valid_identifier(frame.session_id) || !valid_digest(frame.digest) ||
      !digest_matches(frame.digest, payload_json, payload_length)) {
    return false;
  }
  char reply[16] = {};
  if (frame.has_reply_to) {
    if (frame.reply_to == 0) return false;
    std::snprintf(reply, sizeof(reply), "%lu", static_cast<unsigned long>(frame.reply_to));
  } else {
    std::strncpy(reply, "null", sizeof(reply) - 1);
  }
  const int written = std::snprintf(
      output, output_capacity,
      "{\"boot_id\":\"%s\",\"digest\":\"%s\",\"payload\":%.*s,\"reply_to\":%s,\"seq\":%lu,\"session_id\":\"%s\",\"type\":\"%s\",\"v\":%u}\n",
      frame.boot_id, frame.digest, static_cast<int>(payload_length), payload_json, reply,
      static_cast<unsigned long>(frame.sequence), frame.session_id, frame.type,
      static_cast<unsigned>(frame.version));
  if (written < 0 || static_cast<std::size_t>(written) >= output_capacity ||
      static_cast<std::size_t>(written) > kMaxLineBytes) {
    return false;
  }
  output_length = static_cast<std::size_t>(written);
  return true;
}

ProtocolSession::ProtocolSession(const char* boot_id, const char* session_id, std::size_t queue_capacity)
    : queue_capacity_(queue_capacity > kQueueCapacity ? kQueueCapacity : queue_capacity) {
  reset(boot_id, session_id);
}

void ProtocolSession::reset(const char* boot_id, const char* session_id) {
  std::strncpy(boot_id_, boot_id == nullptr ? "" : boot_id, sizeof(boot_id_) - 1);
  std::strncpy(session_id_, session_id == nullptr ? "" : session_id, sizeof(session_id_) - 1);
  boot_id_[sizeof(boot_id_) - 1] = '\0';
  session_id_[sizeof(session_id_) - 1] = '\0';
  last_received_sequence_ = 0;
  recent_count_ = 0;
  recent_cursor_ = 0;
  pending_count_ = 0;
}

void ProtocolSession::prime_received(uint32_t sequence) {
  last_received_sequence_ = sequence;
  recent_count_ = sequence == 0 ? 0 : 1;
  recent_cursor_ = 0;
  recent_[0] = sequence;
}

bool ProtocolSession::seen(uint32_t sequence) const {
  for (std::size_t index = 0; index < recent_count_; ++index) if (recent_[index] == sequence) return true;
  return false;
}

void ProtocolSession::remember(uint32_t sequence) {
  if (recent_count_ < kRecentSequenceCapacity) recent_[recent_count_++] = sequence;
  else {
    recent_[recent_cursor_] = sequence;
    recent_cursor_ = (recent_cursor_ + 1) % kRecentSequenceCapacity;
  }
}

Result ProtocolSession::accept(const uint8_t* line, std::size_t length, bool dispatch) {
  Result result;
  return accept(line, length, result, dispatch);
}

Result& ProtocolSession::accept(const uint8_t* line, std::size_t length, Result& result, bool dispatch) {
  FrameCodec::decode(line, length, result);
  if (!result.accepted) return result;

  const bool is_hello = std::strcmp(result.frame.type, "hello") == 0;
  const bool new_session = is_hello &&
                           (session_id_[0] == '\0' ||
                            std::strcmp(result.frame.session_id, session_id_) != 0);
  if (new_session) {
    // Hello is the sole session bootstrap.  The host's hello boot identifier
    // is intentionally not compared with the device boot identifier; all
    // subsequent frames must use this session and this device boot.
    std::strncpy(session_id_, result.frame.session_id, sizeof(session_id_) - 1);
    session_id_[sizeof(session_id_) - 1] = '\0';
    last_received_sequence_ = 0;
    recent_count_ = 0;
    recent_cursor_ = 0;
    pending_count_ = 0;
    result.session_transition = true;
  } else {
    if (std::strcmp(result.frame.boot_id, boot_id_) != 0) {
      result.accepted = false;
      result.reason = RejectReason::BootMismatch;
      return result;
    }
    if (std::strcmp(result.frame.session_id, session_id_) != 0) {
      result.accepted = false;
      result.reason = RejectReason::SessionMismatch;
      return result;
    }
  }
  if (seen(result.frame.sequence)) {
    result.accepted = false;
    result.reason = RejectReason::Duplicate;
    return result;
  }
  if (result.frame.sequence <= last_received_sequence_) {
    result.accepted = false;
    result.reason = RejectReason::OutOfOrder;
    return result;
  }
  if (dispatch && pending_count_ >= queue_capacity_) {
    result.accepted = false;
    result.reason = RejectReason::QueueFull;
    return result;
  }
  last_received_sequence_ = result.frame.sequence;
  remember(result.frame.sequence);
  if (dispatch) {
    ++pending_count_;
    result.dispatched = true;
  }
  return result;
}

bool ProtocolSession::complete() {
  if (pending_count_ == 0) return false;
  --pending_count_;
  return true;
}

std::size_t ProtocolSession::discard_pending() {
  const std::size_t discarded = pending_count_;
  pending_count_ = 0;
  return discarded;
}

}  // namespace phase1::protocol
