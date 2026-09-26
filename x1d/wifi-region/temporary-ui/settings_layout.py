"""First layout pass; preserves existing setting delegates and device bindings."""

def apply_layout(source):
    start = source.index('        // Section header')
    end = source.index('            MouseArea {', start)
    source = source[:start] + '''        // Group separator belongs above the left-aligned caption.
        section.delegate: Item {
            width: list.width
            height: 56
            Rectangle {
                x: 0; y: 8; width: parent.width; height: 1
                color: constants.menuSubMenuColor
            }
            Text {
                id: subHeaderText
                x: 0; y: 18; width: parent.width; height: 30
                text: section
                font.family: constants.menuSubHeaderFontName
                font.pixelSize: 22
                horizontalAlignment: Text.AlignLeft
                verticalAlignment: Text.AlignVCenter
                color: constants.menuSubMenuColor
            }
''' + source[end:]
    # Only labels change alignment; value formatting and control handlers stay intact.
    for item_id in ('dropDownText', 'boolText'):
        start = source.index('id: ' + item_id)
        end = source.index('font.family:', start)
        block = source[start:end]
        assert 'horizontalAlignment: Text.AlignRight' in block
        block = block.replace('horizontalAlignment: Text.AlignRight',
                              'horizontalAlignment: Text.AlignLeft')
        block = block.replace(' + ":"', '')
        source = source[:start] + block + source[end:]
    return source
