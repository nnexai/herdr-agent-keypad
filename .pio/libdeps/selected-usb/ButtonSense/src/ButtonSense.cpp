#include "ButtonSense.h"

namespace button
{

void ButtonSense::begin(uint8_t pin, bool activeLow, bool enablePullup)
{
    _pin = pin;
    _activeLow = activeLow;
    if (enablePullup && activeLow) {
        pinMode(pin, INPUT_PULLUP);
    } else {
        pinMode(pin, INPUT);
    }
}

void ButtonSense::begin(InitCallbackFunction initCallback)
{
    if (initCallback) initCallback();
}

void ButtonSense::setButtonStateFunction(StateCallbackFunction f)
{
    _stateCallback = f;
}

bool ButtonSense::_readDebounced()
{
    bool logical;
    if (_stateCallback) {
        logical = _stateCallback() != 0;
    } else {
        bool raw = digitalRead(_pin);
        logical = _activeLow ? !raw : raw;
    }

    if (logical != _rawState) {
        _rawState = logical;
        _lastRawChangeMs = _lastMs;
    }

    if (_lastMs - _lastRawChangeMs >= _debounceMs) {
        _debouncedState = logical;
    }

    return _debouncedState;
}

void ButtonSense::update(uint32_t msec)
{
    _currentState = state_nochange;
    _lastMs = msec;
    bool pressed = _readDebounced();

    Event triggerEvent = EVENT_NONE;
    _oldPress = _press;

    // --- 按压状态转化 ---
    if (pressed) {
        uint32_t holdDuration = _lastMs - _lastChangeMs;

        if (_oldPress == 0) {
            // 从释放转为按下
            _press = 1;
            _lastChangeMs = _lastMs;
            _holdReported = false;
            triggerEvent = EVENT_PRESSED;
        } else {
            _lastHoldPeriod = holdDuration;
            if (_oldPress == 1 && holdDuration >= _holdMs) {
                // 短按升级为长按
                _press = 2;
                triggerEvent = EVENT_HOLD;
                _holdReported = true;
                _lastHoldRepeatMs = _lastMs;
            } else if (_oldPress == 2 && _holdRepeatMs > 0) {
                // 长按中，周期性触发 repeat
                if (_lastMs - _lastHoldRepeatMs >= _holdRepeatMs) {
                    _lastHoldRepeatMs = _lastMs;
                    triggerEvent = EVENT_HOLD_REPEAT;
                }
            }
        }
    } else {
        if (_oldPress > 0) {
            _press = 0;
            _lastChangeMs = _lastMs;
            _lastHoldRepeatMs = 0;

            if (_oldPress == 1) {
                // 短按释放 → click
                _lastClickedMs = _lastMs;
                ++_clickCount;
                triggerEvent = EVENT_CLICKED;
            } else if (_oldPress == 2) {
                // 长按后释放
                triggerEvent = EVENT_RELEASED_AFTER_HOLD;
            }
        }
    }

    // 触发当前事件回调
    if (triggerEvent != EVENT_NONE) {
        _emit(triggerEvent);
    }

    // --- 连击超时判定 ---
    uint16_t multiClickTimeout = (_multiClickTimeoutMs > 0) ? _multiClickTimeoutMs : _holdMs;
    if (_clickCount > 0 && _press == 0 && (_lastMs - _lastClickedMs >= multiClickTimeout)) {
        if (_clickCount == 1) {
            _emit(EVENT_SINGLE_CLICKED);
        } else if (_clickCount == 2) {
            _emit(EVENT_DOUBLE_CLICKED);
        }

        if (_clickCount >= 1) {
            _emit(EVENT_MULTI_CLICKED);
        }

        _clickCount = 0;
    }
}

void ButtonSense::_emit(Event event)
{
    switch (event) {
        case EVENT_CLICKED:
            _currentState = state_clicked;
        break;

        case EVENT_HOLD:
            _currentState = state_hold;
        break;

        case EVENT_MULTI_CLICKED:
            _currentState = state_decide_click_count;
            _decidedClickCount = _clickCount;
        break;

        default: break;
    }

    if (_callback) {
        _callback(*this, event);
    }
}

} // namespace button
