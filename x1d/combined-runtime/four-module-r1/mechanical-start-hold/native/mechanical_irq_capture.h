#ifndef HBL_MECHANICAL_IRQ_CAPTURE_H
#define HBL_MECHANICAL_IRQ_CAPTURE_H
#include "mechanical_irq_wire.h"
#define HBL_MECH_IRQ_MAGIC UINT32_C(0x32494d47)
#define HBL_MECH_IRQ_BITS UINT32_C(0x0c000000)
struct HblMechanicalIrqRecord {
    uint32_t magic, armed, stage, sequence;
    struct HblMechanicalSync sample;
    uint32_t queued, dropped, seen, previous;
    uint32_t configured, priority, targets, config;
    uint32_t handler90, argument90, handler91, argument91;
};
_Static_assert(sizeof(struct HblMechanicalIrqRecord)==108,"IRQ record ABI");
#endif
