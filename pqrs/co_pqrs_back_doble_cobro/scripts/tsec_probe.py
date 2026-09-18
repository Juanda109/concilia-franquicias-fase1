"""Sonda del TSEC del modulo doble cobro contra el ASO configurado.

Uso:  python tsec_probe.py <customer_id> <product_id> <AAAAMMDD>

No modifica nada: solo pide el TSEC y hace las dos llamadas (financial-overview
y operations) mostrando si el token viaja y que responde el ASO.
"""
import asyncio, logging, os, sys

sys.path.insert(0, "src")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

# El .env lo carga config.py (dotenv). El servicio lo importa via
# analysis_service; aqui hay que hacerlo explicito o las DC_ASO_API_* van vacias.
import infrastructure.core.config  # noqa: E402,F401

from infrastructure.persistence.doble_cobro_aso_client import (  # noqa: E402
    DobleCobroAsoClient, _tsec_debug,
)


async def main() -> int:
    customer = sys.argv[1] if len(sys.argv) > 1 else "13083558"
    product = sys.argv[2] if len(sys.argv) > 2 else "00130766000200022384"
    day = sys.argv[3] if len(sys.argv) > 3 else "20260806"

    client = DobleCobroAsoClient()
    print("=" * 72)
    print("base_url          :", client.base_url)
    print("ticket_url        :", os.getenv("DC_ASO_TICKET_URL") or f"{client.base_url}/TechArchitecture/co/grantingTicket/V02")
    print("fo_path           :", client.financial_overview_path)
    print("operations_path   :", client.operations_path)
    print("timeout (s)       :", client.timeout)
    print("ASO_SOURCE        :", os.getenv("ASO_SOURCE") or "(sin definir -> simulator)")
    print("api_user_id       :", os.getenv("DC_ASO_API_USER_ID") or "(VACIO)")
    print("api_consumer_id   :", os.getenv("DC_ASO_API_CONSUMER_ID") or "(VACIO)")
    print("api_auth_type     :", os.getenv("DC_ASO_API_AUTHENTICATION_TYPE") or "(VACIO)")
    print("api_password      :", "(definida)" if os.getenv("DC_ASO_API_PASSWORD") else "(VACIA)")
    print("=" * 72)

    # ---- 1. grantingTicket -------------------------------------------------
    print("\n[1] grantingTicket")
    tsec = await client.get_tsec()
    dbg = _tsec_debug(tsec)
    print("   ->", dbg)
    if not tsec:
        print("   !! TSEC VACIO: las llamadas siguientes saldran SIN header tsec")

    # ---- 2. financial-overview --------------------------------------------
    print("\n[2] financial-overview")
    fo = await client.financial_overview(customer_id=customer)
    if fo is None:
        print("   -> None (fallo; ver traza ASO ERROR arriba)")
    else:
        contracts = ((fo.get("data") or {}).get("contracts")) or fo.get("data") or []
        print(f"   -> OK, contracts={len(contracts) if isinstance(contracts, list) else 'n/d'}")

    # ---- 3. operations -----------------------------------------------------
    print("\n[3] operations")
    is_card = len(product) == 16 and product.isdigit()
    ops = await client.operations(
        operation_date=day,
        card_id=product if is_card else "",
        account_id="" if is_card else product,
    )
    if ops is None:
        print("   -> None (fallo; ver traza ASO ERROR arriba)")
    else:
        print(f"   -> OK, bloques={len(ops.get('data') or [])}")

    # ---- 4. ¿el backend VALIDA el tsec? -----------------------------------
    print("\n[4] control: misma llamada con un tsec basura y sin tsec")
    basura = await client._get(
        client.financial_overview_path, {"customer.id": customer},
        tsec="TSEC-INVALIDO-DE-PRUEBA", operation="control_basura",
    )
    sin = await client._get(
        client.financial_overview_path, {"customer.id": customer},
        tsec=None, operation="control_sin_tsec",
    )
    print("   con tsec basura ->", "acepta" if basura is not None else "rechaza")
    print("   sin tsec        ->", "acepta" if sin is not None else "rechaza")
    if basura is not None and sin is not None:
        print("   VEREDICTO: este backend NO valida el tsec (tipico del simulador).")
        print("              Que el flujo funcione aqui NO prueba que el TSEC sirva.")
    else:
        print("   VEREDICTO: este backend SI valida el tsec.")
    return 0


sys.exit(asyncio.run(main()))
