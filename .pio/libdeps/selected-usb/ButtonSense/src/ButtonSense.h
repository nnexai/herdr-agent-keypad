#ifndef __BUTTON_SENSE_H__
#define __BUTTON_SENSE_H__

#include <Arduino.h>
#include <cstdint>

namespace button
{

typedef std::function<void()> InitCallbackFunction;
typedef std::function<uint8_t()> StateCallbackFunction;

class ButtonSense
{
public:
    /// 按键事件类型
    enum Event : uint8_t {
        EVENT_NONE = 0,          ///< 无事件
        EVENT_PRESSED,           ///< 刚按下（去抖后首次检测到按下）
        EVENT_RELEASED,          ///< 刚释放
        EVENT_CLICKED,           ///< 短按点击（按下后快速释放）
        EVENT_HOLD,              ///< 长按开始（按住超过 hold 阈值）
        EVENT_HOLD_REPEAT,       ///< 长按重复触发（按住期间周期性触发）
        EVENT_SINGLE_CLICKED,    ///< 单击已确定
        EVENT_DOUBLE_CLICKED,    ///< 双击已确定
        EVENT_MULTI_CLICKED,     ///< 多次连击已确定（配合 getClickCount 读取次数）
        EVENT_RELEASED_AFTER_HOLD, ///< 长按后释放
        EVENT_COUNT              ///< 事件类型总数（内部使用）
    };

    /// 回调函数类型
    /// @param btn  触发事件的 ButtonSense 对象引用
    /// @param event  事件类型
    typedef void (*Callback)(ButtonSense& btn, Event event);

    /// @brief 构造函数
    ButtonSense() {}

#ifdef ARDUINO
    /// @brief 初始化按键 GPIO
    void begin(uint8_t pin, bool activeLow = true, bool enablePullup = true);
#endif

    /// @brief 初始化按键（支持扩展器等外设）
    /// @param initCallback 可选的初始化回调函数，在 begin() 时调用，适用于 I2C/SPI 扩展器、触摸传感器等需要特殊初始化的场景
    void begin(InitCallbackFunction initCallback = nullptr);

    void setButtonStateFunction(StateCallbackFunction f);

#ifdef ARDUINO
    /// @brief 在 loop() 中周期性调用，读取 GPIO 并更新状态机
    void update() { update(millis()); }
#endif

    void update(std::uint32_t msec);

    /// @brief 注册事件回调
    void onEvent(Callback cb) { _callback = cb; }

    // ---- 配置参数 ----

    /// @brief 设置去抖时间（毫秒），默认 10ms
    void setDebounceThresh(uint32_t msec) { _debounceMs = msec; }
    uint32_t getDebounceThresh() const    { return _debounceMs; }

    /// @brief 设置长按判定时间（毫秒），默认 500ms
    void setHoldThresh(uint32_t msec) { _holdMs = msec; }
    uint32_t getHoldThresh() const    { return _holdMs; }

    /// @brief 设置长按重复间隔（毫秒），默认 200ms；设为 0 则禁用重复触发
    void setHoldRepeatMs(uint16_t ms)  { _holdRepeatMs = ms; }
    uint16_t getHoldRepeatMs() const   { return _holdRepeatMs; }

    /// @brief 设置连击判定超时（毫秒），默认等于 holdMs
    void setMultiClickTimeoutMs(uint16_t ms) { _multiClickTimeoutMs = ms; }
    uint16_t getMultiClickTimeoutMs() const  { return _multiClickTimeoutMs; }

    /// 按键状态
    enum button_state_t : uint8_t
    {
        state_nochange = 0,        ///< 本次 update 无显著事件
        state_clicked,             ///< 短按释放（即时，不等待连击超时）
        state_hold,                ///< 长按开始
        state_decide_click_count,  ///< 连击次数已确定（单击 / 双击 / 多击）
    };

    // ---- 轮询式事件检测 ----

    /// @brief 短按释放（即时，每次 click 都触发，不区分单双击）
    bool wasClicked()          const { return _currentState == state_clicked; }

    /// @brief 长按开始
    bool wasHold()             const { return _currentState == state_hold; }

    /// @brief 单击已确定（等待连击超时后确认）
    bool wasSingleClicked()    const { return _currentState == state_decide_click_count && _decidedClickCount == 1; }

    /// @brief 双击已确定
    bool wasDoubleClicked()    const { return _currentState == state_decide_click_count && _decidedClickCount == 2; }

    /// @brief 连击次数已确定（单/双/多击通用）
    bool wasDecideClickCount() const { return _currentState == state_decide_click_count; }

    /// @brief 连击次数；在 wasDecideClickCount() 为 true 的 loop 周期内有效
    uint8_t getClickCount() const {
        return (_currentState == state_decide_click_count) ? _decidedClickCount : _clickCount;
    }

    /// ---- 即时状态查询 ----
    /// Returns true if the button is currently held pressed.
    bool isHolding()   const { return _press == 2; }
    bool wasChangePressed()  const { return ((bool)_press) != ((bool)_oldPress); }

    bool isPressed()   const { return _press != 0; }
    bool isReleased()  const { return _press == 0; }
    bool wasPressed()        const { return !_oldPress && _press; }
    bool wasReleased()       const { return _oldPress && !_press; }
    bool wasReleasedAfterHold() const { return !_press && _oldPress == 2; }
    bool wasReleaseFor(uint32_t ms) const { return _oldPress && !_press && _lastHoldPeriod >= ms; }

    bool pressedFor(uint32_t ms)  const { return _press  && (_lastMs - _lastChangeMs >= ms); }
    bool releasedFor(uint32_t ms) const { return !_press && (_lastMs - _lastChangeMs >= ms); }

    button_state_t getState() const { return _currentState; }

    uint32_t getLastChangeMs() const { return _lastChangeMs; }
    uint32_t getUpdateMs()     const { return _lastMs; }

    /// @brief 获取绑定的 GPIO 引脚
    uint8_t getPin() const { return _pin; }

private:
    /// @brief 内部触发回调
    void _emit(Event event);

    /// @brief 读取去抖后的电平
    bool _readDebounced();

    uint8_t  _pin;
    bool     _activeLow;
    uint32_t _lastMs           = 0;
    uint32_t _lastChangeMs     = 0;
    uint32_t _lastRawChangeMs  = 0;
    uint32_t _lastClickedMs    = 0;
    uint32_t _lastHoldRepeatMs = 0;
    uint16_t _debounceMs       = 10;
    uint16_t _holdMs           = 500;
    uint16_t _holdRepeatMs     = 200;
    uint16_t _multiClickTimeoutMs = 0;  // 0 = use _holdMs
    uint16_t _lastHoldPeriod   = 0;
    bool     _rawState         = false;
    bool     _debouncedState   = false;
    uint8_t        _press              = 0;   // 0=release, 1=short press, 2=holding
    uint8_t        _oldPress           = 0;
    uint8_t        _clickCount         = 0;
    uint8_t        _decidedClickCount  = 0;
    bool           _holdReported       = false;
    Callback              _callback           = nullptr;
    StateCallbackFunction _stateCallback      = nullptr;
    button_state_t        _currentState       = state_nochange;
};

} // namespace button

#endif
