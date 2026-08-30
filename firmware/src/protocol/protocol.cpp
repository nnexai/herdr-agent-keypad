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
    else if (std::strcmp(key, "capabilities") == 0) bit = 1U << 28;
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
    } else if (bit == (1U << 28)) {
      if (!cursor.take('[')) return RejectReason::InvalidShape;
      uint8_t count = 0;
      cursor.ws();
      if (!cursor.take(']')) {
        while (true) {
          char capability[33] = {};
          if (!cursor.string(capability, sizeof(capability)) || std::strlen(capability) == 0) {
            return RejectReason::InvalidShape;
          }
          if (++count > 8) return RejectReason::InvalidShape;
          cursor.ws();
          if (cursor.take(']')) break;
          if (!cursor.take(',')) return RejectReason::InvalidJson;
        }
      }
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

  uint32_t expected = 0;
  const char* type = frame.type;
  if (std::strcmp(type, "hello") == 0) expected = (1U << 1) | (1U << 2) | (1U << 3);
  else if (std::strcmp(type, "hello_ack") == 0) {
    expected = (1U << 0) | (1U << 1) | (1U << 2) | (1U << 3);
  }
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
  if (std::strcmp(type, "hello_ack") == 0) {
    if (mask != expected && mask != (expected | (1U << 28))) return RejectReason::InvalidShape;
  } else if (mask != expected || payload_end == nullptr) {
    return RejectReason::InvalidShape;
  }
  if (payload_end == nullptr) return RejectReason::InvalidShape;
  frame.payload_length = static_cast<std::size_t>(payload_end - payload_start);
  if (!copy_text(frame.payload_text, sizeof(frame.payload_text), payload_start, frame.payload_length)) return RejectReason::LineTooLong;
  return RejectReason::Ok;
}
bool valid_opaque(const char* value, bool allow_empty = false) {
  const std::size_t length = std::strlen(value);
  if ((!allow_empty && length == 0) || length > kMaxIdentifierBytes) return false;
  for (std::size_t index = 0; index < length; ++index) {
    const unsigned char c = static_cast<unsigned char>(value[index]);
    if (c < 0x21 || c >= 0x80) return false;
  }
  return true;
}

bool parse_optional_opaque(Cursor& cursor, char* output, std::size_t capacity) {
  cursor.ws();
  if (cursor.p < cursor.end && *cursor.p == 'n') {
    if (!cursor.null_value()) return false;
    output[0] = '\0';
    return true;
  }
  return cursor.string(output, capacity) && valid_opaque(output);
}

bool valid_source_status(const char* value) {
  return std::strcmp(value, "current") == 0 || std::strcmp(value, "empty") == 0 ||
         std::strcmp(value, "stale") == 0 || std::strcmp(value, "unavailable") == 0 ||
         std::strcmp(value, "offline") == 0;
}

bool valid_agent_state(const char* value) {
  return std::strcmp(value, "empty") == 0 || std::strcmp(value, "working") == 0 ||
         std::strcmp(value, "idle") == 0 || std::strcmp(value, "blocked") == 0 ||
         std::strcmp(value, "finished") == 0 || std::strcmp(value, "settled") == 0 ||
         std::strcmp(value, "unknown") == 0;
}

bool valid_codex_state(const char* value) {
  return std::strcmp(value, "current") == 0 || std::strcmp(value, "stale") == 0 ||
         std::strcmp(value, "unavailable") == 0 || std::strcmp(value, "auth_required") == 0 ||
         std::strcmp(value, "codex_offline") == 0 || std::strcmp(value, "host_offline") == 0;
}

bool valid_link_state(const char* value) {
  return std::strcmp(value, "current") == 0 || std::strcmp(value, "offline") == 0;
}

bool valid_error_code(const char* value) {
  if (value[0] == '\0') return true;
  if (std::strlen(value) != 6 || value[0] != 'E' || value[1] != '-') return false;
  uint32_t code = 0;
  for (uint8_t index = 2; index < 6; ++index) {
    if (value[index] < '0' || value[index] > '9') return false;
    code = code * 10U + static_cast<uint32_t>(value[index] - '0');
  }
  return code >= 2400 && code <= 2410;
}

bool valid_suffix(const char* value) {
  const std::size_t length = std::strlen(value);
  if (length == 0 || length > 6) return false;
  for (std::size_t index = 0; index < length; ++index) {
    const char c = value[index];
    if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) return false;
  }
  return true;
}

RejectReason parse_v2_codex(Cursor& cursor) {
  if (!cursor.take('{')) return RejectReason::InvalidShape;
  uint32_t mask = 0;
  char source_state[20] = {};
  char reset_text[33] = {};
  char observation_age[17] = {};
  char error_code[17] = {};
  bool reached = false;
  bool reached_present = false;
  bool primary_present = false;
  bool secondary_present = false;
  bool primary_claim = false;
  bool secondary_claim = false;
  while (true) {
    cursor.ws();
    if (cursor.take('}')) break;
    char key[32] = {};
    if (!cursor.string(key, sizeof(key)) || !cursor.take(':')) return RejectReason::InvalidJson;
    uint32_t bit = 0;
    if (std::strcmp(key, "source_state") == 0) bit = 1U << 0;
    else if (std::strcmp(key, "primary") == 0) bit = 1U << 1;
    else if (std::strcmp(key, "secondary") == 0) bit = 1U << 2;
    else if (std::strcmp(key, "reset_text") == 0) bit = 1U << 3;
    else if (std::strcmp(key, "observation_age") == 0) bit = 1U << 4;
    else if (std::strcmp(key, "reached_limit") == 0) bit = 1U << 5;
    else if (std::strcmp(key, "error_code") == 0) bit = 1U << 6;
    else return RejectReason::UnknownField;
    if ((mask & bit) != 0) return RejectReason::DuplicateKey;
    mask |= bit;
    if (bit == (1U << 0)) {
      if (!cursor.string(source_state, sizeof(source_state)) || !valid_codex_state(source_state)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 1)) {
      primary_present = true;
      cursor.ws();
      if (cursor.p < cursor.end && *cursor.p == 'n') {
        if (!cursor.null_value()) return RejectReason::InvalidShape;
      } else {
        uint32_t value = 0;
        if (!cursor.uint32(value) || value > 100) return RejectReason::InvalidShape;
        primary_claim = true;
      }
    } else if (bit == (1U << 2)) {
      secondary_present = true;
      cursor.ws();
      if (cursor.p < cursor.end && *cursor.p == 'n') {
        if (!cursor.null_value()) return RejectReason::InvalidShape;
      } else {
        uint32_t value = 0;
        if (!cursor.uint32(value) || value > 100) return RejectReason::InvalidShape;
        secondary_claim = true;
      }
    } else if (bit == (1U << 3)) {
      if (!cursor.string(reset_text, sizeof(reset_text)) || std::strlen(reset_text) == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 4)) {
      if (!cursor.string(observation_age, sizeof(observation_age)) || std::strlen(observation_age) == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 5)) {
      reached_present = true;
      cursor.ws();
      if (cursor.p < cursor.end && *cursor.p == 'n') {
        if (!cursor.null_value()) return RejectReason::InvalidShape;
      } else if (!cursor.boolean(reached)) {
        return RejectReason::InvalidShape;
      }
    } else if (!cursor.string(error_code, sizeof(error_code)) || !valid_error_code(error_code)) {
      return RejectReason::InvalidShape;
    }
    cursor.ws();
    if (cursor.take('}')) break;
    if (!cursor.take(',')) return RejectReason::InvalidJson;
  }
  if (mask != 0x7fU || !primary_present || !secondary_present || !reached_present) return RejectReason::InvalidShape;
  if (std::strcmp(error_code, "E-2401") == 0 &&
      (std::strcmp(source_state, "unavailable") != 0 || primary_claim || secondary_claim ||
       std::strcmp(reset_text, "RESET N/A") != 0 || reached)) return RejectReason::InvalidShape;
  return RejectReason::Ok;
}

bool valid_copilot_state(const char* value) {
  return std::strcmp(value, "current") == 0 || std::strcmp(value, "stale") == 0 ||
         std::strcmp(value, "auth_required") == 0 || std::strcmp(value, "unavailable") == 0;
}

bool valid_copilot_reason(const char* value) {
  static constexpr const char* kReasons[] = {
      "", "auth_required", "cli_missing", "cli_version_mismatch",
      "protocol_mismatch", "unsupported_host", "quota_unavailable",
      "billing_mode_unsupported", "malformed_quota", "timeout",
      "transport_unavailable"};
  for (const char* reason : kReasons) if (std::strcmp(value, reason) == 0) return true;
  return false;
}

RejectReason parse_v2_copilot(Cursor& cursor) {
  if (!cursor.take('{')) return RejectReason::InvalidShape;
  uint32_t mask = 0;
  uint32_t used = 0;
  uint32_t included = 0;
  uint32_t percent = 0;
  bool used_present = false;
  bool included_present = false;
  bool percent_present = false;
  bool unlimited = false;
  bool reached = false;
  bool usage_allowed = false;
  bool overage_allowed = false;
  bool reached_present = false;
  bool usage_allowed_present = false;
  bool overage_allowed_present = false;
  char source_state[20] = {};
  char reset_text[33] = {};
  char observation_age[17] = {};
  char failure_reason[33] = {};
  while (true) {
    cursor.ws();
    if (cursor.take('}')) break;
    char key[32] = {};
    if (!cursor.string(key, sizeof(key)) || !cursor.take(':')) return RejectReason::InvalidJson;
    uint32_t bit = 0;
    if (std::strcmp(key, "source_state") == 0) bit = 1U << 0;
    else if (std::strcmp(key, "used_credits") == 0) bit = 1U << 1;
    else if (std::strcmp(key, "included_credits") == 0) bit = 1U << 2;
    else if (std::strcmp(key, "used_percent") == 0) bit = 1U << 3;
    else if (std::strcmp(key, "reset_text") == 0) bit = 1U << 4;
    else if (std::strcmp(key, "observation_age") == 0) bit = 1U << 5;
    else if (std::strcmp(key, "unlimited") == 0) bit = 1U << 6;
    else if (std::strcmp(key, "reached_limit") == 0) bit = 1U << 7;
    else if (std::strcmp(key, "usage_allowed") == 0) bit = 1U << 8;
    else if (std::strcmp(key, "overage_allowed") == 0) bit = 1U << 9;
    else if (std::strcmp(key, "failure_reason") == 0) bit = 1U << 10;
    else return RejectReason::UnknownField;
    if ((mask & bit) != 0) return RejectReason::DuplicateKey;
    mask |= bit;
    if (bit == (1U << 0)) {
      if (!cursor.string(source_state, sizeof(source_state)) || !valid_copilot_state(source_state)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 1) || bit == (1U << 2)) {
      bool& present = bit == (1U << 1) ? used_present : included_present;
      uint32_t& value = bit == (1U << 1) ? used : included;
      present = true;
      cursor.ws();
      if (cursor.p < cursor.end && *cursor.p == 'n') {
        if (!cursor.null_value()) return RejectReason::InvalidShape;
        present = false;
      } else if (!cursor.uint32(value) || value > 1000000000UL) {
        return RejectReason::InvalidShape;
      }
    } else if (bit == (1U << 3)) {
      percent_present = true;
      cursor.ws();
      if (cursor.p < cursor.end && *cursor.p == 'n') {
        if (!cursor.null_value()) return RejectReason::InvalidShape;
        percent_present = false;
      } else if (!cursor.uint32(percent) || percent > 100) {
        return RejectReason::InvalidShape;
      }
    } else if (bit == (1U << 4)) {
      if (!cursor.string(reset_text, sizeof(reset_text)) || std::strlen(reset_text) == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 5)) {
      if (!cursor.string(observation_age, sizeof(observation_age)) || std::strlen(observation_age) == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 6)) {
      if (!cursor.boolean(unlimited)) return RejectReason::InvalidShape;
    } else if (bit >= (1U << 7) && bit <= (1U << 9)) {
      bool* value = bit == (1U << 7) ? &reached : bit == (1U << 8) ? &usage_allowed : &overage_allowed;
      bool* present = bit == (1U << 7) ? &reached_present : bit == (1U << 8) ? &usage_allowed_present : &overage_allowed_present;
      *present = true;
      cursor.ws();
      if (cursor.p < cursor.end && *cursor.p == 'n') {
        if (!cursor.null_value()) return RejectReason::InvalidShape;
        *present = false;
      } else if (!cursor.boolean(*value)) {
        return RejectReason::InvalidShape;
      }
    } else if (!cursor.string(failure_reason, sizeof(failure_reason)) || !valid_copilot_reason(failure_reason)) {
      return RejectReason::InvalidShape;
    }
    cursor.ws();
    if (cursor.take('}')) break;
    if (!cursor.take(',')) return RejectReason::InvalidJson;
  }
  if (mask != 0x7ffU || !reached_present || !usage_allowed_present || !overage_allowed_present) return RejectReason::InvalidShape;
  if (std::strcmp(source_state, "auth_required") == 0 || std::strcmp(source_state, "unavailable") == 0) {
    if (used_present || included_present || percent_present || unlimited || reached_present && reached) return RejectReason::InvalidShape;
  }
  if (unlimited && included_present) return RejectReason::InvalidShape;
  return RejectReason::Ok;
}

RejectReason parse_v2_diagnostics(Cursor& cursor) {
  if (!cursor.take('{')) return RejectReason::InvalidShape;
  uint32_t mask = 0;
  char link_status[16] = {};
  char herdr_status[16] = {};
  char codex_status[20] = {};
  char sync_age[17] = {};
  char codex_age[17] = {};
  char firmware_version[17] = {};
  char bridge_version[17] = {};
  char device_suffix[7] = {};
  char session_suffix[7] = {};
  char revision_suffix[7] = {};
  char error_code[17] = {};
  while (true) {
    cursor.ws();
    if (cursor.take('}')) break;
    char key[32] = {};
    if (!cursor.string(key, sizeof(key)) || !cursor.take(':')) return RejectReason::InvalidJson;
    uint32_t bit = 0;
    if (std::strcmp(key, "link_status") == 0) bit = 1U << 0;
    else if (std::strcmp(key, "herdr_status") == 0) bit = 1U << 1;
    else if (std::strcmp(key, "codex_status") == 0) bit = 1U << 2;
    else if (std::strcmp(key, "sync_age") == 0) bit = 1U << 3;
    else if (std::strcmp(key, "codex_age") == 0) bit = 1U << 4;
    else if (std::strcmp(key, "firmware_version") == 0) bit = 1U << 5;
    else if (std::strcmp(key, "protocol_version") == 0) bit = 1U << 6;
    else if (std::strcmp(key, "bridge_version") == 0) bit = 1U << 7;
    else if (std::strcmp(key, "device_suffix") == 0) bit = 1U << 8;
    else if (std::strcmp(key, "session_suffix") == 0) bit = 1U << 9;
    else if (std::strcmp(key, "revision_suffix") == 0) bit = 1U << 10;
    else if (std::strcmp(key, "error_code") == 0) bit = 1U << 11;
    else return RejectReason::UnknownField;
    if ((mask & bit) != 0) return RejectReason::DuplicateKey;
    mask |= bit;
    if (bit == (1U << 0)) {
      if (!cursor.string(link_status, sizeof(link_status)) || !valid_link_state(link_status)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 1)) {
      if (!cursor.string(herdr_status, sizeof(herdr_status)) || !valid_source_status(herdr_status)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 2)) {
      if (!cursor.string(codex_status, sizeof(codex_status)) || !valid_codex_state(codex_status)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 3)) {
      if (!cursor.string(sync_age, sizeof(sync_age)) || std::strlen(sync_age) == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 4)) {
      if (!cursor.string(codex_age, sizeof(codex_age)) || std::strlen(codex_age) == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 5)) {
      if (!cursor.string(firmware_version, sizeof(firmware_version)) || std::strlen(firmware_version) == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 6)) {
      uint32_t value = 0;
      if (!cursor.uint32(value) || value != 2) return RejectReason::InvalidShape;
    } else if (bit == (1U << 7)) {
      if (!cursor.string(bridge_version, sizeof(bridge_version)) || std::strlen(bridge_version) == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 8)) {
      if (!cursor.string(device_suffix, sizeof(device_suffix)) || !valid_suffix(device_suffix)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 9)) {
      if (!cursor.string(session_suffix, sizeof(session_suffix)) || !valid_suffix(session_suffix)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 10)) {
      if (!cursor.string(revision_suffix, sizeof(revision_suffix)) || !valid_suffix(revision_suffix)) return RejectReason::InvalidShape;
    } else if (!cursor.string(error_code, sizeof(error_code)) || !valid_error_code(error_code)) {
      return RejectReason::InvalidShape;
    }
    cursor.ws();
    if (cursor.take('}')) break;
    if (!cursor.take(',')) return RejectReason::InvalidJson;
  }
  return mask == 0xfffU ? RejectReason::Ok : RejectReason::InvalidShape;
}

RejectReason parse_v2_agent(Cursor& cursor) {
  if (!cursor.take('{')) return RejectReason::InvalidPayload;
  uint32_t mask = 0;
  uint32_t slot = 0;
  uint32_t source_revision = 0;
  char entry_id[kMaxIdentifierBytes + 1] = {};
  char title[kMaxPayloadStringBytes + 1] = {};
  char discriminator[33] = {};
  char since[17] = {};
  char age[17] = {};
  char state[16] = {};
  char pane_id[kMaxIdentifierBytes + 1] = {};
  char terminal_id[kMaxIdentifierBytes + 1] = {};
  char agent_session[kMaxIdentifierBytes + 1] = {};
  while (true) {
    cursor.ws();
    if (cursor.take('}')) break;
    char key[32] = {};
    if (!cursor.string(key, sizeof(key)) || !cursor.take(':')) return RejectReason::InvalidJson;
    uint32_t bit = 0;
    if (std::strcmp(key, "slot") == 0) bit = 1U << 0;
    else if (std::strcmp(key, "entry_id") == 0) bit = 1U << 1;
    else if (std::strcmp(key, "title") == 0) bit = 1U << 2;
    else if (std::strcmp(key, "discriminator") == 0) bit = 1U << 3;
    else if (std::strcmp(key, "since") == 0) bit = 1U << 4;
    else if (std::strcmp(key, "age") == 0) bit = 1U << 5;
    else if (std::strcmp(key, "state") == 0) bit = 1U << 6;
    else if (std::strcmp(key, "pane_id") == 0) bit = 1U << 7;
    else if (std::strcmp(key, "terminal_id") == 0) bit = 1U << 8;
    else if (std::strcmp(key, "agent_session") == 0) bit = 1U << 9;
    else if (std::strcmp(key, "source_revision") == 0) bit = 1U << 10;
    else return RejectReason::UnknownField;
    if ((mask & bit) != 0) return RejectReason::DuplicateKey;
    mask |= bit;
    if (bit == (1U << 0)) {
      if (!cursor.uint32(slot) || slot > 2) return RejectReason::InvalidShape;
    } else if (bit == (1U << 1)) {
      if (!cursor.string(entry_id, sizeof(entry_id))) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 2)) {
      if (!cursor.string(title, sizeof(title)) || std::strlen(title) == 0 || std::strlen(title) > 64) return RejectReason::InvalidShape;
    } else if (bit == (1U << 3)) {
      if (!cursor.string(discriminator, sizeof(discriminator)) || std::strlen(discriminator) == 0 || std::strlen(discriminator) > 32) return RejectReason::InvalidShape;
    } else if (bit == (1U << 4)) {
      if (!cursor.string(since, sizeof(since)) || std::strlen(since) > 16) return RejectReason::InvalidShape;
    } else if (bit == (1U << 5)) {
      if (!cursor.string(age, sizeof(age)) || std::strlen(age) > 16) return RejectReason::InvalidShape;
    } else if (bit == (1U << 6)) {
      if (!cursor.string(state, sizeof(state)) || !valid_agent_state(state)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 7)) {
      if (!cursor.string(pane_id, sizeof(pane_id))) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 8)) {
      if (!cursor.string(terminal_id, sizeof(terminal_id))) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 9)) {
      if (!parse_optional_opaque(cursor, agent_session, sizeof(agent_session))) return RejectReason::InvalidIdentifier;
    } else {
      if (!cursor.uint32(source_revision)) return RejectReason::InvalidShape;
    }
    cursor.ws();
    if (cursor.take('}')) break;
    if (!cursor.take(',')) return RejectReason::InvalidJson;
  }
  if (mask != 0x7ffU) return RejectReason::InvalidShape;
  const bool empty = std::strcmp(state, "empty") == 0;
  if (!valid_opaque(entry_id, empty) || !valid_opaque(pane_id, empty) ||
      !valid_opaque(terminal_id, empty) ||
      (!empty && source_revision == 0) || (empty && source_revision != 0)) {
    return RejectReason::InvalidIdentifier;
  }
  return RejectReason::Ok;
}
RejectReason parse_v2_payload(Cursor& cursor, Frame& frame, const char* payload_start) {
  if (!cursor.take('{')) return RejectReason::InvalidPayload;
  bool accepted = false;
  bool focused = false;
  uint32_t mask = 0;
  uint32_t snapshot_revision = 0;
  uint32_t slot = 0;
  uint32_t source_revision = 0;
  bool has_codex = false;
  bool has_copilot = false;
  bool has_diagnostics = false;
  char host_epoch[kMaxIdentifierBytes + 1] = {};
  char source_status[16] = {};
  char reason[kMaxPayloadStringBytes + 1] = {};
  char action_id[kMaxIdentifierBytes + 1] = {};
  char entry_id[kMaxIdentifierBytes + 1] = {};
  char pane_id[kMaxIdentifierBytes + 1] = {};
  char terminal_id[kMaxIdentifierBytes + 1] = {};
  char agent_session[kMaxIdentifierBytes + 1] = {};
  char outcome[24] = {};
  while (true) {
    cursor.ws();
    if (cursor.take('}')) break;
    char key[32] = {};
    if (!cursor.string(key, sizeof(key)) || !cursor.take(':')) return RejectReason::InvalidJson;
    uint32_t bit = 0;
    if (std::strcmp(key, "host_epoch") == 0) bit = 1U << 0;
    else if (std::strcmp(key, "snapshot_revision") == 0) bit = 1U << 1;
    else if (std::strcmp(key, "source_status") == 0) bit = 1U << 2;
    else if (std::strcmp(key, "agents") == 0) bit = 1U << 3;
    else if (std::strcmp(key, "accepted") == 0) bit = 1U << 4;
    else if (std::strcmp(key, "reason") == 0) bit = 1U << 5;
    else if (std::strcmp(key, "action_id") == 0) bit = 1U << 6;
    else if (std::strcmp(key, "outcome") == 0) bit = 1U << 7;
    else if (std::strcmp(key, "slot") == 0) bit = 1U << 8;
    else if (std::strcmp(key, "entry_id") == 0) bit = 1U << 9;
    else if (std::strcmp(key, "pane_id") == 0) bit = 1U << 10;
    else if (std::strcmp(key, "terminal_id") == 0) bit = 1U << 11;
    else if (std::strcmp(key, "agent_session") == 0) bit = 1U << 12;
    else if (std::strcmp(key, "source_revision") == 0) bit = 1U << 13;
    else if (std::strcmp(key, "focused") == 0) bit = 1U << 14;
    else if (std::strcmp(key, "codex") == 0) bit = 1U << 15;
    else if (std::strcmp(key, "diagnostics") == 0) bit = 1U << 16;
    else if (std::strcmp(key, "copilot") == 0) bit = 1U << 17;
    else return RejectReason::UnknownField;
    if ((mask & bit) != 0) return RejectReason::DuplicateKey;
    mask |= bit;
    if (bit == (1U << 0)) {
      if (!cursor.string(host_epoch, sizeof(host_epoch)) || !valid_opaque(host_epoch)) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 1)) {
      if (!cursor.uint32(snapshot_revision) || snapshot_revision == 0) return RejectReason::InvalidShape;
    } else if (bit == (1U << 2)) {
      if (!cursor.string(source_status, sizeof(source_status)) || !valid_source_status(source_status)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 3)) {
      if (!cursor.take('[')) return RejectReason::InvalidPayload;
      for (uint8_t index = 0; index < 3; ++index) {
        const RejectReason row = parse_v2_agent(cursor);
        if (row != RejectReason::Ok) return row;
        cursor.ws();
        if (index < 2) {
          if (!cursor.take(',')) return RejectReason::InvalidShape;
        } else if (!cursor.take(']')) {
          return RejectReason::InvalidShape;
        }
      }
    } else if (bit == (1U << 15)) {
      const RejectReason codex_reason = parse_v2_codex(cursor);
      if (codex_reason != RejectReason::Ok) return codex_reason;
      has_codex = true;
    } else if (bit == (1U << 16)) {
      const RejectReason diagnostics_reason = parse_v2_diagnostics(cursor);
      if (diagnostics_reason != RejectReason::Ok) return diagnostics_reason;
      has_diagnostics = true;
    } else if (bit == (1U << 17)) {
      const RejectReason copilot_reason = parse_v2_copilot(cursor);
      if (copilot_reason != RejectReason::Ok) return copilot_reason;
      has_copilot = true;
    } else if (bit == (1U << 4)) {
      if (!cursor.boolean(accepted)) return RejectReason::InvalidShape;
    } else if (bit == (1U << 5)) {
      if (!cursor.string(reason, sizeof(reason)) || std::strlen(reason) == 0 || std::strlen(reason) > 64) return RejectReason::InvalidShape;
    } else if (bit == (1U << 6)) {
      if (!cursor.string(action_id, sizeof(action_id)) || !valid_opaque(action_id)) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 7)) {
      if (!cursor.string(outcome, sizeof(outcome))) return RejectReason::InvalidShape;
    } else if (bit == (1U << 8)) {
      if (!cursor.uint32(slot) || slot > 2) return RejectReason::InvalidShape;
    } else if (bit == (1U << 9)) {
      if (!cursor.string(entry_id, sizeof(entry_id)) || !valid_opaque(entry_id)) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 10)) {
      if (!cursor.string(pane_id, sizeof(pane_id)) || !valid_opaque(pane_id)) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 11)) {
      if (!cursor.string(terminal_id, sizeof(terminal_id)) || !valid_opaque(terminal_id)) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 12)) {
      if (!parse_optional_opaque(cursor, agent_session, sizeof(agent_session))) return RejectReason::InvalidIdentifier;
    } else if (bit == (1U << 13)) {
      if (!cursor.uint32(source_revision) || source_revision == 0) return RejectReason::InvalidShape;
    } else if (!cursor.boolean(focused)) {
      return RejectReason::InvalidShape;
    }
    cursor.ws();
    if (cursor.take('}')) break;
    if (!cursor.take(',')) return RejectReason::InvalidJson;
  }
  uint32_t expected = 0;
  if (std::strcmp(frame.type, "agent_snapshot") == 0) {
    expected = (1U << 0) | (1U << 1) | (1U << 2) | (1U << 3);
    if (has_codex != has_diagnostics) return RejectReason::InvalidShape;
    if (has_copilot && !has_codex) return RejectReason::InvalidShape;
    if (has_codex) expected |= (1U << 15) | (1U << 16);
    if (has_copilot) expected |= (1U << 17);
  } else if (std::strcmp(frame.type, "snapshot_ack") == 0) expected = (1U << 0) | (1U << 1) | (1U << 2) | (1U << 4) | (1U << 5);
  else if (std::strcmp(frame.type, "focus_intent") == 0) expected = (1U << 0) | (1U << 1) | (1U << 6) | (1U << 8) | (1U << 9) | (1U << 10) | (1U << 11) | (1U << 12) | (1U << 13);
  else if (std::strcmp(frame.type, "focus_result") == 0) expected = (1U << 0) | (1U << 1) | (1U << 6) | (1U << 7) | (1U << 8) | (1U << 9) | (1U << 10) | (1U << 11) | (1U << 12) | (1U << 13) | (1U << 14);
  else return RejectReason::UnknownType;
  if (mask != expected) return RejectReason::InvalidShape;
  if (std::strcmp(frame.type, "focus_result") == 0 && std::strcmp(outcome, "accepted") == 0 && !focused) return RejectReason::InvalidShape;
  frame.payload_length = static_cast<std::size_t>(cursor.p - payload_start);
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
      if (value != 1 && value != 2) {
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
  if (result.frame.version != 1 && result.frame.version != 2) {
    result.reason = RejectReason::InvalidVersion;
    return result;
  }
  const bool known_v1_type = std::strcmp(result.frame.type, "hello") == 0 || std::strcmp(result.frame.type, "hello_ack") == 0 ||
                             std::strcmp(result.frame.type, "probe") == 0 || std::strcmp(result.frame.type, "probe_ack") == 0 ||
                             std::strcmp(result.frame.type, "event") == 0 || std::strcmp(result.frame.type, "error") == 0 ||
                             std::strcmp(result.frame.type, "metrics") == 0 || std::strcmp(result.frame.type, "metrics_ack") == 0;
  const bool known_v2_type = std::strcmp(result.frame.type, "agent_snapshot") == 0 || std::strcmp(result.frame.type, "snapshot_ack") == 0 ||
                             std::strcmp(result.frame.type, "focus_intent") == 0 || std::strcmp(result.frame.type, "focus_result") == 0;
  if (result.frame.version == 1 && !known_v1_type) {
    result.reason = RejectReason::UnknownType;
    return result;
  }
  if (result.frame.version == 2 && !known_v2_type) {
    result.reason = known_v1_type ? RejectReason::InvalidVersion : RejectReason::UnknownType;
    return result;
  }
  {
    Cursor payload_cursor{result.frame.payload_text, result.frame.payload_text + result.frame.payload_length};
    const RejectReason payload_reason = result.frame.version == 2
                                            ? parse_v2_payload(payload_cursor, result.frame, result.frame.payload_text)
                                            : parse_payload(payload_cursor, result.frame, result.frame.payload_text);
    if (payload_reason != RejectReason::Ok) {
      result.reason = payload_reason;
      return result;
    }
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
      payload_length == 0 || payload_length >= kMaxLineBytes || (frame.version != 1 && frame.version != 2) ||
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
