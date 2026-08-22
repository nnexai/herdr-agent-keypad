#include <unity.h>

#include <cstdint>
#include <fstream>
#include <string>
#include <cstring>

#include "protocol/protocol.h"

#ifndef PHASE1_GOLDEN_FIXTURE
#error "PHASE1_GOLDEN_FIXTURE must point at the repository fixture"
#endif

namespace {

using phase1::protocol::FrameCodec;
using phase1::protocol::ProtocolSession;
using phase1::protocol::RejectReason;
using phase1::protocol::Result;

bool field_string(const std::string& object, const char* key, std::string& value) {
  const std::string marker = std::string("\"") + key + "\":\"";
  const std::size_t start = object.find(marker);
  if (start == std::string::npos) return false;
  const std::size_t value_start = start + marker.size();
  value.clear();
  bool escaped = false;
  for (std::size_t index = value_start; index < object.size(); ++index) {
    const char c = object[index];
    if (escaped) {
      if (c == 'n') value.push_back('\n');
      else if (c == 'r') value.push_back('\r');
      else if (c == 't') value.push_back('\t');
      else value.push_back(c);
      escaped = false;
    } else if (c == '\\') {
      escaped = true;
    } else if (c == '"') {
      return true;
    } else {
      value.push_back(c);
    }
  }
  return false;
}

bool field_bool(const std::string& object, const char* key, bool& value) {
  const std::string marker = std::string("\"") + key + "\":";
  const std::size_t start = object.find(marker);
  if (start == std::string::npos) return false;
  const std::size_t value_start = start + marker.size();
  if (object.compare(value_start, 4, "true") == 0) {
    value = true;
    return true;
  }
  if (object.compare(value_start, 5, "false") == 0) {
    value = false;
    return true;
  }
  return false;
}

bool field_uint(const std::string& object, const char* key, uint32_t& value) {
  const std::string marker = std::string("\"") + key + "\":";
  const std::size_t start = object.find(marker);
  if (start == std::string::npos) return false;
  std::size_t index = start + marker.size();
  uint64_t parsed = 0;
  bool any = false;
  while (index < object.size() && object[index] >= '0' && object[index] <= '9') {
    any = true;
    parsed = parsed * 10U + static_cast<unsigned>(object[index++] - '0');
  }
  if (!any || parsed > 0xffffffffULL) return false;
  value = static_cast<uint32_t>(parsed);
  return true;
}
bool make_v2_line(const char* type, const char* boot_id, const char* session_id, uint32_t sequence,
                  const char* payload, uint32_t reply_to, std::string& output) {
  phase1::protocol::Frame frame;
  frame.version = 2;
  if (std::strlen(type) >= sizeof(frame.type) ||
      std::strlen(boot_id) > phase1::protocol::kMaxIdentifierBytes ||
      std::strlen(session_id) > phase1::protocol::kMaxIdentifierBytes) {
    return false;
  }
  std::strncpy(frame.type, type, sizeof(frame.type) - 1);
  std::strncpy(frame.boot_id, boot_id, sizeof(frame.boot_id) - 1);
  std::strncpy(frame.session_id, session_id, sizeof(frame.session_id) - 1);
  frame.sequence = sequence;
  frame.reply_to = reply_to;
  frame.has_reply_to = reply_to != 0;
  phase1::protocol::FrameCodec::format_digest(
      phase1::protocol::FrameCodec::digest_payload(payload, std::strlen(payload)),
      frame.digest);
  char encoded[phase1::protocol::kMaxLineBytes + 1] = {};
  std::size_t encoded_length = 0;
  if (!phase1::protocol::FrameCodec::encode(
          frame, payload, std::strlen(payload), encoded, sizeof(encoded), encoded_length)) {
    return false;
  }
  output.assign(encoded, encoded_length);
  return true;
}

void assert_vector(const std::string& vector) {
  std::string id;
  std::string line;
  std::string expected;
  std::string expected_boot = "boot-a";
  std::string expected_session = "session-a";
  TEST_ASSERT_TRUE(field_string(vector, "id", id));
  TEST_ASSERT_TRUE(field_string(vector, "line", line));
  TEST_ASSERT_TRUE(field_string(vector, "reason", expected));
  field_string(vector, "expected_boot_id", expected_boot);
  field_string(vector, "expected_session_id", expected_session);
  uint32_t prior = 0;
  field_uint(vector, "prior_seq", prior);
  bool expected_dispatch = false;
  field_bool(vector, "dispatch", expected_dispatch);

  if (line == "synthetic:oversized") line.assign(4096, 'x'), line.push_back('\n');
  ProtocolSession session(expected_boot.c_str(), expected_session.c_str(), 4);
  session.prime_received(prior);
  const Result result = session.accept(reinterpret_cast<const uint8_t*>(line.data()), line.size());
  TEST_ASSERT_EQUAL_STRING(expected.c_str(), phase1::protocol::rejection_name(result.reason));
  TEST_ASSERT_EQUAL(expected == "ok", result.accepted);
  TEST_ASSERT_EQUAL(expected_dispatch, result.dispatched);
  (void)id;
}

void test_fixture_vectors(void) {
  std::ifstream fixture(PHASE1_GOLDEN_FIXTURE);
  TEST_ASSERT_TRUE_MESSAGE(fixture.good(), "golden fixture must be readable");
  std::string line;
  std::size_t count = 0;
  while (std::getline(fixture, line)) {
    if (line.find("\"id\":") == std::string::npos) continue;
    assert_vector(line);
    ++count;
  }
  TEST_ASSERT_EQUAL_UINT(40, count);
}

#ifndef PHASE2_GOLDEN_FIXTURE
#error "PHASE2_GOLDEN_FIXTURE must point at the repository fixture"
#endif

void test_v2_fixture_vectors(void) {
  std::ifstream fixture(PHASE2_GOLDEN_FIXTURE);
  TEST_ASSERT_TRUE_MESSAGE(fixture.good(), "v2 golden fixture must be readable");
  std::string vector;
  std::size_t count = 0;
  while (std::getline(fixture, vector)) {
    if (vector.find("\"id\":\"v2_") == std::string::npos) continue;
    std::string line;
    std::string expected;
    TEST_ASSERT_TRUE(field_string(vector, "line", line));
    TEST_ASSERT_TRUE(field_string(vector, "reason", expected));
    if (line == "synthetic:oversized") line.assign(4096, 'x'), line.push_back('\n');
    ProtocolSession session("boot-a", "session-a", 4);
    const Result result = session.accept(reinterpret_cast<const uint8_t*>(line.data()), line.size());
    TEST_ASSERT_EQUAL_STRING(expected.c_str(), phase1::protocol::rejection_name(result.reason));
    ++count;
  }
  TEST_ASSERT_EQUAL_UINT(6, count);
}

void test_valid_encode_decode_and_reset(void) {
  std::ifstream fixture(PHASE1_GOLDEN_FIXTURE);
  std::string vector;
  std::string encoded;
  while (std::getline(fixture, vector)) {
    if (vector.find("\"id\":\"valid_probe\"") != std::string::npos) {
      TEST_ASSERT_TRUE(field_string(vector, "line", encoded));
      break;
    }
  }
  TEST_ASSERT_FALSE(encoded.empty());
  const Result decoded = FrameCodec::decode(reinterpret_cast<const uint8_t*>(encoded.data()), encoded.size());
  TEST_ASSERT_TRUE(decoded.accepted);
  char output[phase1::protocol::kMaxLineBytes + 1] = {};
  std::size_t output_length = 0;
  TEST_ASSERT_TRUE(FrameCodec::encode(decoded.frame, decoded.frame.payload_text, decoded.frame.payload_length, output, sizeof(output), output_length));
  TEST_ASSERT_EQUAL_UINT(encoded.size(), output_length);
  TEST_ASSERT_EQUAL_STRING(encoded.c_str(), output);

  ProtocolSession session("boot-a", "session-a", 4);
  Result accepted = session.accept(reinterpret_cast<const uint8_t*>(encoded.data()), encoded.size());
  TEST_ASSERT_TRUE(accepted.accepted);
  TEST_ASSERT_EQUAL_UINT(1, session.pending_count());
  session.reset("boot-new", "session-new");
  TEST_ASSERT_EQUAL_UINT(0, session.pending_count());
  TEST_ASSERT_EQUAL_UINT(0, session.last_received_sequence());
}

void test_rejects_wide_version_and_trailing_bytes(void) {
  std::ifstream fixture(PHASE1_GOLDEN_FIXTURE);
  std::string vector;
  std::string line;
  while (std::getline(fixture, vector)) {
    if (vector.find("\"id\":\"valid_probe\"") != std::string::npos) {
      TEST_ASSERT_TRUE(field_string(vector, "line", line));
      break;
    }
  }
  TEST_ASSERT_FALSE(line.empty());
  std::string wide_version = line;
  const std::size_t version = wide_version.rfind("\"v\":1}");
  TEST_ASSERT_TRUE(version != std::string::npos);
  wide_version.replace(version, 6, "\"v\":257}");
  const Result wide = FrameCodec::decode(
      reinterpret_cast<const uint8_t*>(wide_version.data()), wide_version.size());
  TEST_ASSERT_FALSE(wide.accepted);
  TEST_ASSERT_EQUAL_STRING("invalid_version", phase1::protocol::rejection_name(wide.reason));

  std::string trailing = line;
  trailing.insert(trailing.size() - 1, " garbage");
  const Result extra = FrameCodec::decode(
      reinterpret_cast<const uint8_t*>(trailing.data()), trailing.size());
  TEST_ASSERT_FALSE(extra.accepted);
  TEST_ASSERT_EQUAL_STRING("invalid_json", phase1::protocol::rejection_name(extra.reason));
}

void test_queue_bound_completion_and_bootstrap(void) {
  std::ifstream fixture(PHASE1_GOLDEN_FIXTURE);
  std::string vector;
  std::string hello_line;
  std::string probe_line;
  while (std::getline(fixture, vector)) {
    if (vector.find("\"id\":\"valid_hello\"") != std::string::npos) {
      TEST_ASSERT_TRUE(field_string(vector, "line", hello_line));
    } else if (vector.find("\"id\":\"valid_probe\"") != std::string::npos) {
      TEST_ASSERT_TRUE(field_string(vector, "line", probe_line));
    }
  }
  TEST_ASSERT_FALSE(hello_line.empty());
  TEST_ASSERT_FALSE(probe_line.empty());

  ProtocolSession bootstrap("boot-a", "", 2);
  const Result hello = bootstrap.accept(
      reinterpret_cast<const uint8_t*>(hello_line.data()), hello_line.size());
  TEST_ASSERT_TRUE(hello.accepted);
  TEST_ASSERT_TRUE(hello.session_transition);
  TEST_ASSERT_EQUAL_UINT(1, bootstrap.pending_count());
  TEST_ASSERT_TRUE(bootstrap.complete());

  const Result probe = bootstrap.accept(
      reinterpret_cast<const uint8_t*>(probe_line.data()), probe_line.size());
  TEST_ASSERT_TRUE(probe.accepted);
  TEST_ASSERT_EQUAL_UINT(1, bootstrap.pending_count());
  TEST_ASSERT_TRUE(bootstrap.complete());

  const Result decoded = FrameCodec::decode(
      reinterpret_cast<const uint8_t*>(probe_line.data()), probe_line.size());
  TEST_ASSERT_TRUE(decoded.accepted);
  auto frame_for = [&](uint32_t sequence, char* output, std::size_t& length) {
    phase1::protocol::Frame frame = decoded.frame;
    frame.sequence = sequence;
    TEST_ASSERT_TRUE(FrameCodec::encode(frame, frame.payload_text, frame.payload_length,
                                        output, phase1::protocol::kMaxLineBytes + 1, length));
  };
  char first[phase1::protocol::kMaxLineBytes + 1] = {};
  char second[phase1::protocol::kMaxLineBytes + 1] = {};
  char third[phase1::protocol::kMaxLineBytes + 1] = {};
  std::size_t first_length = 0;
  std::size_t second_length = 0;
  std::size_t third_length = 0;
  frame_for(4, first, first_length);
  frame_for(5, second, second_length);
  frame_for(6, third, third_length);

  ProtocolSession bounded("boot-a", "session-a", 2);
  TEST_ASSERT_TRUE(bounded.accept(reinterpret_cast<const uint8_t*>(first), first_length).accepted);
  TEST_ASSERT_TRUE(bounded.accept(reinterpret_cast<const uint8_t*>(second), second_length).accepted);
  const Result full = bounded.accept(reinterpret_cast<const uint8_t*>(third), third_length);
  TEST_ASSERT_FALSE(full.accepted);
  TEST_ASSERT_EQUAL_STRING("queue_full", phase1::protocol::rejection_name(full.reason));
  TEST_ASSERT_EQUAL_UINT(2, bounded.pending_count());
  TEST_ASSERT_TRUE(bounded.complete());
  const Result restored = bounded.accept(reinterpret_cast<const uint8_t*>(third), third_length);
  TEST_ASSERT_TRUE(restored.accepted);
  TEST_ASSERT_EQUAL_UINT(2, bounded.pending_count());
}

void test_closed_v2_types_and_descriptorless_hold_authority(void) {
  const char* intent_payload =
      "{\"action_id\":\"action-a\",\"agent_session\":null,\"entry_id\":\"w19:p1\","
      "\"host_epoch\":\"epoch-a\",\"pane_id\":\"w19:p1\",\"slot\":0,"
      "\"snapshot_revision\":1,\"source_revision\":1,\"terminal_id\":\"term_6593907102c45d\"}";
  const char* ack_payload =
      "{\"accepted\":true,\"host_epoch\":\"epoch-a\",\"snapshot_revision\":1,"
      "\"source_status\":\"empty\",\"reason\":\"committed\"}";
  const char* result_payload =
      "{\"action_id\":\"action-a\",\"agent_session\":null,\"entry_id\":\"w19:p1\","
      "\"focused\":true,\"host_epoch\":\"epoch-a\",\"outcome\":\"accepted\","
      "\"pane_id\":\"w19:p1\",\"slot\":0,\"snapshot_revision\":1,"
      "\"source_revision\":1,\"terminal_id\":\"term_6593907102c45d\"}";
  std::string vector;
  std::string snapshot_line;
  std::ifstream fixture(PHASE2_GOLDEN_FIXTURE);
  TEST_ASSERT_TRUE(fixture.good());
  while (std::getline(fixture, vector)) {
    if (vector.find("\"id\":\"v2_valid_snapshot\"") != std::string::npos) {
      TEST_ASSERT_TRUE(field_string(vector, "line", snapshot_line));
      break;
    }
  }
  TEST_ASSERT_FALSE(snapshot_line.empty());
  const Result snapshot = FrameCodec::decode(
      reinterpret_cast<const uint8_t*>(snapshot_line.data()), snapshot_line.size());
  TEST_ASSERT_TRUE(snapshot.accepted);
  TEST_ASSERT_EQUAL_STRING("agent_snapshot", snapshot.frame.type);

  std::string ack_line;
  std::string intent_line;
  std::string result_line;
  TEST_ASSERT_TRUE(make_v2_line("snapshot_ack", "boot-a", "session-a", 2, ack_payload, 1, ack_line));
  TEST_ASSERT_TRUE(make_v2_line("focus_intent", "boot-a", "session-a", 3, intent_payload, 0, intent_line));
  TEST_ASSERT_TRUE(make_v2_line("focus_result", "boot-a", "session-a", 4, result_payload, 3, result_line));
  for (const std::string* line : {&ack_line, &intent_line, &result_line}) {
    const Result accepted = FrameCodec::decode(
        reinterpret_cast<const uint8_t*>(line->data()), line->size());
    TEST_ASSERT_TRUE(accepted.accepted);
  }

  const char* unknown_types[] = {
      "hold", "hid", "keyboard", "keycode", "text", "macro", "command", "provider",
  };
  for (const char* type : unknown_types) {
    std::string line;
    TEST_ASSERT_TRUE(make_v2_line(type, "boot-a", "session-a", 5, "{}", 0, line));
    const Result rejected = FrameCodec::decode(
        reinterpret_cast<const uint8_t*>(line.data()), line.size());
    TEST_ASSERT_FALSE(rejected.accepted);
    TEST_ASSERT_EQUAL_STRING("unknown_type", phase1::protocol::rejection_name(rejected.reason));
  }

  const char* forbidden_fields[] = {
      "\"hold\":true", "\"hid\":true", "\"keycode\":32", "\"text\":\"x\"",
      "\"macro\":\"x\"", "\"command\":\"x\"", "\"provider\":\"x\"",
      "\"timing_ms\":550", "\"owner\":\"key-1\"", "\"lifecycle\":\"hold\"",
      "\"direction\":\"device_to_host\"",
  };
  for (const char* field : forbidden_fields) {
    std::string payload = intent_payload;
    payload.insert(payload.size() - 1, std::string(",") + field);
    std::string line;
    TEST_ASSERT_TRUE(make_v2_line("focus_intent", "boot-a", "session-a", 6, payload.c_str(), 0, line));
    const Result rejected = FrameCodec::decode(
        reinterpret_cast<const uint8_t*>(line.data()), line.size());
    TEST_ASSERT_FALSE(rejected.accepted);
    TEST_ASSERT_EQUAL_STRING("invalid_shape", phase1::protocol::rejection_name(rejected.reason));
  }

  std::string oversized(phase1::protocol::kMaxLineBytes, 'x');
  oversized.push_back('\n');
  const Result too_long = FrameCodec::decode(
      reinterpret_cast<const uint8_t*>(oversized.data()), oversized.size());
  TEST_ASSERT_FALSE(too_long.accepted);
  TEST_ASSERT_EQUAL_STRING("line_too_long", phase1::protocol::rejection_name(too_long.reason));

}

void test_v2_session_boot_sequence_and_duplicate_fences(void) {
  const char* intent_payload =
      "{\"action_id\":\"action-a\",\"agent_session\":null,\"entry_id\":\"w19:p1\","
      "\"host_epoch\":\"epoch-a\",\"pane_id\":\"w19:p1\",\"slot\":0,"
      "\"snapshot_revision\":1,\"source_revision\":1,\"terminal_id\":\"term_6593907102c45d\"}";
  std::string line;
  ProtocolSession session("boot-a", "session-a", 8);

  TEST_ASSERT_TRUE(make_v2_line("focus_intent", "wrong-boot", "session-a", 1, intent_payload, 0, line));
  Result rejected = session.accept(reinterpret_cast<const uint8_t*>(line.data()), line.size());
  TEST_ASSERT_FALSE(rejected.accepted);
  TEST_ASSERT_EQUAL_STRING("boot_mismatch", phase1::protocol::rejection_name(rejected.reason));

  TEST_ASSERT_TRUE(make_v2_line("focus_intent", "boot-a", "wrong-session", 1, intent_payload, 0, line));
  rejected = session.accept(reinterpret_cast<const uint8_t*>(line.data()), line.size());
  TEST_ASSERT_FALSE(rejected.accepted);
  TEST_ASSERT_EQUAL_STRING("session_mismatch", phase1::protocol::rejection_name(rejected.reason));

  TEST_ASSERT_TRUE(make_v2_line("focus_intent", "boot-a", "session-a", 3, intent_payload, 0, line));
  Result accepted = session.accept(reinterpret_cast<const uint8_t*>(line.data()), line.size());
  TEST_ASSERT_TRUE(accepted.accepted);

  Result duplicate = session.accept(reinterpret_cast<const uint8_t*>(line.data()), line.size());
  TEST_ASSERT_FALSE(duplicate.accepted);
  TEST_ASSERT_EQUAL_STRING("duplicate", phase1::protocol::rejection_name(duplicate.reason));

  TEST_ASSERT_TRUE(make_v2_line("focus_intent", "boot-a", "session-a", 2, intent_payload, 0, line));
  Result out_of_order = session.accept(reinterpret_cast<const uint8_t*>(line.data()), line.size());
  TEST_ASSERT_FALSE(out_of_order.accepted);
  TEST_ASSERT_EQUAL_STRING("out_of_order", phase1::protocol::rejection_name(out_of_order.reason));
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_fixture_vectors);
  RUN_TEST(test_v2_fixture_vectors);
  RUN_TEST(test_valid_encode_decode_and_reset);
  RUN_TEST(test_rejects_wide_version_and_trailing_bytes);
  RUN_TEST(test_closed_v2_types_and_descriptorless_hold_authority);
  RUN_TEST(test_v2_session_boot_sequence_and_duplicate_fences);
  RUN_TEST(test_queue_bound_completion_and_bootstrap);
  return UNITY_END();
}
