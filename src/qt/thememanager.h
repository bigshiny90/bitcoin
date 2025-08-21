// Copyright (c) 2024 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_QT_THEMEMANAGER_H
#define BITCOIN_QT_THEMEMANAGER_H

#include <QObject>
#include <QString>
#include <QColor>

QT_BEGIN_NAMESPACE
class QApplication;
QT_END_NAMESPACE

/**
 * Manages application theming using Qt Style Sheets (QSS).
 * Loads theme files and applies them based on system dark/light mode.
 */
class ThemeManager : public QObject
{
    Q_OBJECT

public:
    // Theme color definitions
    struct ThemeColors {
        QColor red;
        QColor green;
        QColor yellow;
        QColor orange;
        QColor blue;
    };

    // Graph colors for MempoolStats (with alpha)
    struct GraphColors {
        QColor orange;
        QColor green;
        QColor blue;
    };

    // Static theme definitions
    inline static const ThemeColors LIGHT_THEME_COLORS = {
        .red = QColor("#FF0000"),
        .green = QColor("#007D32"),
        .yellow = QColor("#FFFF80"),
        .orange = QColor("#D85C01"),
        .blue = QColor("#023DCC"),
    };

    inline static const ThemeColors DARK_THEME_COLORS = {
        .red = QColor("#FF8080"),
        .green = QColor("#45DEB5"),
        .yellow = QColor("#FFFF80"),
        .orange = QColor("#F7931A"),
        .blue = QColor("#89AAFF"),
    };

    inline static const GraphColors LIGHT_GRAPH_COLORS = {
        .orange = QColor(216, 92, 1, 250),
        .green = QColor(0, 125, 50, 250),
        .blue = QColor(2, 61, 204, 250),
    };

    inline static const GraphColors DARK_GRAPH_COLORS = {
        .orange = QColor(247, 147, 26, 250),
        .green = QColor(69, 222, 181, 250),
        .blue = QColor(137, 170, 255, 250),
    };

    static ThemeManager& instance();

    /** Initialize theme manager and load theme files */
    void init();

    /** Check if currently in dark mode */
    bool isDarkMode() const { return m_dark_mode; }

    // Current active theme pointers (public for direct access)
    const ThemeColors *m_current_theme_colors;
    const GraphColors *m_current_graph_colors;

Q_SIGNALS:
    /** Emitted when theme changes */
    void themeChanged(bool dark_mode);

protected:
    /** Event filter to catch application-wide palette changes */
    bool eventFilter(QObject* obj, QEvent* event) override;

private:
    ThemeManager() = default;
    ~ThemeManager() = default;

    ThemeManager(const ThemeManager&) = delete;
    ThemeManager& operator=(const ThemeManager&) = delete;

    /** Apply theme based on current system palette */
    void applyTheme(bool dark_mode);

    /** Handle palette change events from the application */
    void handlePaletteChange();

    QString m_light_stylesheet;
    QString m_dark_stylesheet;
    bool m_dark_mode{false};
};

#endif // BITCOIN_QT_THEMEMANAGER_H