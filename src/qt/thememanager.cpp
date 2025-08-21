// Copyright (c) 2024 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <qt/thememanager.h>
#include <qt/guiutil.h>

#include <QApplication>
#include <QEvent>
#include <QFile>
#include <QPalette>
#include <QRegularExpression>
#include <QTextStream>


ThemeManager& ThemeManager::instance()
{
    static ThemeManager instance;
    return instance;
}

void ThemeManager::init()
{
    // Load theme stylesheets from resources
    QFile lightFile(":/themes/light.qss");
    if (lightFile.open(QIODevice::ReadOnly | QIODevice::Text)) {
        QTextStream stream(&lightFile);
        m_light_stylesheet = stream.readAll();
        lightFile.close();
    }

    QFile darkFile(":/themes/dark.qss");
    if (darkFile.open(QIODevice::ReadOnly | QIODevice::Text)) {
        QTextStream stream(&darkFile);
        m_dark_stylesheet = stream.readAll();
        darkFile.close();
    }

    // Install event filter on the application to catch palette changes
    if (qApp) {
        qApp->installEventFilter(this);
        // Apply initial theme based on current palette
        handlePaletteChange();
    }
}

void ThemeManager::applyTheme(bool dark_mode)
{
    m_dark_mode = dark_mode;

    // Set current theme color pointers
    m_current_theme_colors = dark_mode ? &DARK_THEME_COLORS : &LIGHT_THEME_COLORS;
    m_current_graph_colors = dark_mode ? &DARK_GRAPH_COLORS : &LIGHT_GRAPH_COLORS;

    const QString& stylesheet = dark_mode ? m_dark_stylesheet : m_light_stylesheet;

    // Apply the stylesheet to the application
    if (qApp && !stylesheet.isEmpty()) {
        qApp->setStyleSheet(stylesheet);
    }

    Q_EMIT themeChanged(dark_mode);
}

void ThemeManager::handlePaletteChange()
{
    if (!qApp) return;

    // Detect dark mode using the current palette
    const bool dark_mode = GUIUtil::isDarkMode(qApp->palette().color(QPalette::Window));

    // Only apply theme if it actually changed
    if (dark_mode != m_dark_mode) {
        applyTheme(dark_mode);
    }
}

bool ThemeManager::eventFilter(QObject* obj, QEvent* event)
{
    if (event->type() == QEvent::PaletteChange) {
        handlePaletteChange();
    }
    return QObject::eventFilter(obj, event);
}

