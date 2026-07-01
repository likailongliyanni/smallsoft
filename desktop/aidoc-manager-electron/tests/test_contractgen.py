from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import contractgen  # noqa: E402


TEMPLATE = """产品购销合同
合同编号：DYS20260202-330156
买方：西安稻叶山供应链管理有限公司（以下简称“甲方”）
卖方：舟山旧带鱼供应商有限公司（以下简称“乙方”）
根据《中华人民共和国民法典》，双方就物资采购事宜签订本合同。
1.标的物名称、数量、价格、型号等
备注：价格含税，乙方发票交付时间：付款前。
1.1交付地点：原地址
1.2交货时间：原时间
1.3运输方式：乙方负责运输。
2.付款
2.1付款方式：转账。
2.2付款时间：原付款条件。
2.3本合同货款汇入乙方指定的银行账户：
收款单位：舟山旧带鱼供应商有限公司
开户银行：旧银行
银行账号：000000000000
3.其它约定
3.1双方协商解决争议。
甲方（盖章）：
乙方（盖章）：
"""


class ContractGenerationTests(unittest.TestCase):
    def test_replaces_and_verifies_supplier_payment_and_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "新合同.pdf"
            info = contractgen.generate_contract_pdf(
                template_text=TEMPLATE,
                output_path=output,
                supplier_name="西安鼎瑞环境设备有限公司",
                payee_name="西安鼎瑞环境设备有限公司",
                bank_name="中国建设银行西安分行",
                bank_account="6105 0110 4272 0000 0789",
                support_texts=[],
                line_items=[{
                    "name": "格力空调",
                    "specification": "KFR-35GW",
                    "quantity": 6,
                    "unit": "台",
                    "unit_price": 1000,
                    "remark": "",
                }],
                payment_terms="验收后3个工作日内付全款。",
            )

            with fitz.open(output) as document:
                text = "\n".join(page.get_text() for page in document)
            compact = "".join(text.split())
            self.assertIn("西安鼎瑞环境设备有限公司", compact)
            self.assertIn("中国建设银行西安分行", compact)
            self.assertIn("61050110427200000789", compact)
            self.assertIn("格力空调", compact)
            self.assertNotIn("舟山旧带鱼供应商有限公司", compact)
            self.assertIn("乙方", info["verified_fields"])
            self.assertEqual("西安鼎瑞环境设备有限公司", info["supplier"])

    def test_rejects_payee_that_differs_from_supplier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "错误合同.pdf"
            with self.assertRaisesRegex(RuntimeError, "合同乙方.*收款单位.*不一致"):
                contractgen.generate_contract_pdf(
                    template_text=TEMPLATE,
                    output_path=output,
                    supplier_name="西安鼎瑞环境设备有限公司",
                    payee_name="陕西家和汇鲜商贸有限公司",
                    bank_name="中国建设银行大雁塔南广场支行",
                    bank_account="61050110427200000789",
                    support_texts=[],
                    line_items=[{
                        "name": "格力空调",
                        "specification": "KFR-35GW",
                        "quantity": 6,
                        "unit": "台",
                        "unit_price": 1000,
                        "remark": "",
                    }],
                )
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
