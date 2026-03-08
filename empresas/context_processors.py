from .permissions import get_role, can_all, can_cartas, can_fidei, can_pagos, can_calend

def role_flags(request):
    role = get_role(getattr(request, "user", None))
    return {
        "ROLE": role,                  # 'master' | 'notifier' | 'cartas' | 'fidei' | None
        "CAN_ALL": can_all(role),      # full (master/notifier)
        "CAN_CARTAS": can_cartas(role),
        "CAN_FIDEI": can_fidei(role),
        "CAN_PAGOS": can_pagos(role),
        "CAN_CALENDARIO": can_calend(role),
    }
