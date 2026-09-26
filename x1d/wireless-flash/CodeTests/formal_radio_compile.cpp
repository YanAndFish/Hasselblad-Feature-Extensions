#include "../native/formal_radio.h"
extern "C" FormalRadio *hbl_formal_radio_create(QObject *parent) { return new FormalRadio(parent); }
extern "C" void hbl_formal_radio_destroy(FormalRadio *radio) { delete radio; }
extern "C" bool hbl_formal_radio_open(FormalRadio *radio) { return radio->open(); }
extern "C" bool hbl_formal_radio_select(FormalRadio *radio,unsigned index) { return radio->select(index); }
extern "C" bool hbl_formal_radio_power(FormalRadio *radio) { return radio->sendPower(); }
extern "C" bool hbl_formal_radio_fire(FormalRadio *radio,uint64_t at) { return radio->fire(at); }
extern "C" unsigned hbl_formal_radio_cancel(FormalRadio *radio) { return radio->cancelPending(); }
extern "C" void hbl_formal_radio_close(FormalRadio *radio) { radio->close(); }
