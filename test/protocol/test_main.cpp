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
  TEST_ASSERT_EQUAL_UINT(21, count);
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

void test_queue_bound_and_discard(void) {
  std::ifstream fixture(PHASE1_GOLDEN_FIXTURE);
  std::string vector;
  std::string first;
  while (std::getline(fixture, vector)) {
    if (vector.find("\"id\":\"valid_hello\"") != std::string::npos) {
      TEST_ASSERT_TRUE(field_string(vector, "line", first));
      break;
    }
  }
  ProtocolSession session("boot-a", "session-a", 1);
  Result first_result = session.accept(reinterpret_cast<const uint8_t*>(first.data()), first.size());
  TEST_ASSERT_TRUE(first_result.accepted);
  Result second_result = session.accept(reinterpret_cast<const uint8_t*>(first.data()), first.size());
  TEST_ASSERT_EQUAL_STRING("duplicate", phase1::protocol::rejection_name(second_result.reason));
  TEST_ASSERT_EQUAL_UINT(1, session.discard_pending());
  TEST_ASSERT_EQUAL_UINT(0, session.pending_count());
}

}  // namespace

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_fixture_vectors);
  RUN_TEST(test_valid_encode_decode_and_reset);
  RUN_TEST(test_queue_bound_and_discard);
  return UNITY_END();
}
