#include "ButtonManager.h"

namespace button
{

bool ButtonManager::add(ButtonSense& btn)
{
    if (_count >= MAX_BUTTONS)
    {
        return false;
    }
    _buttons[_count] = &btn;
    ++_count;
    return true;
}

void ButtonManager::update()
{
    _prevMask = _pressedMask;
    _pressedMask = 0;

    // 更新所有按键并构建掩码
    for (uint8_t i = 0; i < _count; ++i)
    {
        if (_buttons[i])
        {
            _buttons[i]->update();
            if (_buttons[i]->isPressed())
            {
                _pressedMask |= (1 << i);
            }
        }
    }

    // 检测组合键注册
    for (uint8_t i = 0; i < _count; ++i)
    {
        uint8_t mask = _comboMasks[i];
        if (mask == 0) continue;

        // 组合键按下：掩码完全匹配 且 之前不匹配
        if (_pressedMask == mask && _prevMask != mask && _comboCallbacks[i])
        {
            _comboCallbacks[i](mask);
        }
    }
}

void ButtonManager::onCombo(uint8_t mask, ComboCallback cb)
{
    for (uint8_t i = 0; i < MAX_BUTTONS; ++i)
    {
        if (_comboCallbacks[i] == nullptr)
        {
            _comboMasks[i] = mask;
            _comboCallbacks[i] = cb;
            return;
        }
    }
}

ButtonSense* ButtonManager::getButton(uint8_t index)
{
    if (index < _count)
    {
        return _buttons[index];
    }
    return nullptr;
}

} // namespace button
