#ifndef __BUTTON_MANAGER_H__
#define __BUTTON_MANAGER_H__

#include "ButtonSense.h"
#include <Arduino.h>

namespace button
{

/// @brief 多按键管理器，支持组合键检测
class ButtonManager
{
public:
    /// 最大管理的按键数量
    static constexpr uint8_t MAX_BUTTONS = 8;

    /// 组合键回调函数类型
    /// @param mask  当前按下的按键位掩码（bit N = Button N）
    typedef void (*ComboCallback)(uint8_t mask);

    ButtonManager() = default;

    /// @brief 注册一个按键
    /// @param btn ButtonSense 对象引用
    /// @return true=成功，false=已满
    bool add(ButtonSense& btn);

    /// @brief 在 loop() 中调用，更新所有按键并检测组合键
    void update();

    /// @brief 获取当前所有按下的按键的位掩码
    uint8_t getPressedMask() const { return _pressedMask; }

    /// @brief 获取上一次的按键位掩码
    uint8_t getPrevMask() const { return _prevMask; }

    /// @brief 当前组合键是否匹配指定掩码
    bool isComboHolding(uint8_t mask) const { return _pressedMask == mask; }

    /// @brief 刚触发了某个组合键（本次 update 首次检测到）
    bool wasComboPressed(uint8_t mask) const
    {
        return _pressedMask == mask && _prevMask != mask;
    }

    /// @brief 刚释放了某个组合键
    bool wasComboReleased(uint8_t mask) const
    {
        return _prevMask == mask && _pressedMask != mask;
    }

    /// @brief 注册组合键回调：当 mask 对应的按键同时按下时触发
    void onCombo(uint8_t mask, ComboCallback cb);

    /// @brief 获取管理的按键数量
    uint8_t getCount() const { return _count; }

    /// @brief 按索引获取按键对象指针
    ButtonSense* getButton(uint8_t index);

private:
    ButtonSense* _buttons[MAX_BUTTONS] = {};
    ComboCallback _comboCallbacks[MAX_BUTTONS] = {};
    uint8_t       _comboMasks[MAX_BUTTONS] = {};
    uint8_t       _count       = 0;
    uint8_t       _pressedMask = 0;
    uint8_t       _prevMask    = 0;
};

} // namespace button

#endif
