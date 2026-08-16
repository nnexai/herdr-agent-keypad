#include <unity.h>

#include <cstdint>
#include <fstream>
#include <string>

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

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_fixture_vectors);
  RUN_TEST(test_valid_encode_decode_and_reset);
  RUN_TEST(test_rejects_wide_version_and_trailing_bytes);
  RUN_TEST(test_queue_bound_completion_and_bootstrap);
  return UNITY_END();
}
