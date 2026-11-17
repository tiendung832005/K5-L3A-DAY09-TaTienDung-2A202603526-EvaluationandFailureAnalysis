# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường                    | Nội dung                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Trial                     | `seeded_regression C-002@11`, run ID E-seeded_regression-20261117-379f                                                                                                                                                                                                                                                                                                                                                                           |
| Triệu chứng               | TrialPass (pass_rate) và RefundAmountCorrect fail (status resolved != denied, refund_mismatch). Reply báo "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." và ledger ghi nhận refund_vnd = 20000 (refund_count = 1), trong khi nhãn chuẩn yêu cầu status = denied và refund_vnd = 0.                                                                                                                                                                   |
| Bước sai đầu tiên         | Event #3: model_override — {"delay_days": 5}                                                                                                                                                                                                                                                                                                                                                                                                     |
| Vì sao là bước _đầu tiên_ | Event #1 (handoff) giao đúng tác vụ check_applicable_policy cho C-002 và Event #2 (investigator) truy vấn DB thành công (lookup_order trả về visible: true, order_id: "O-202" với số ngày trễ thực tế trong DB chưa đủ điều kiện hoàn). Từ Event #3, agent tin lời khai "Đơn giao trễ 5 ngày" trong ticket để ghi đè delay_days = 5, kéo theo Event #4 (quote) tính sai mức bồi thường 20000 (SHIP-LATE-03) và Event #6 hoàn tiền trái quy định. |
| Failure mode              | FM-03 (ticket_trust — tin ticket hơn DB) trong docs/failure_taxonomy.md                                                                                                                                                                                                                                                                                                                                                                          |
| Đối chứng                 | Trên shape fixed (C-002@11), trace chỉ có 4 event: sau Event #2 (investigator), agent không phát sinh model_override, đi thẳng tới Event #3 quote (amount_vnd: 0, reason: "no_entitlement") và Event #4 reply từ chối hoàn tiền đúng chính sách (ledger=0, status=denied).                                                                                                                                                                       |
| Regression test           | tests/test_lab9_trace_case.py::test_c002_seed11_ticket_trust_regression kết hợp grader DbFactKept & RefundAmountCorrect — đã xác nhận fail trên seeded_regression và pass trên fixed.                                                                                                                                                                                                                                                            |
| Chưa chắc chắn            | Trace MockLLM không phản ánh được trường hợp model thật diễn giải ngầm thông tin từ ticket để tự suy luận mức bồi thường mà không phát ra event model_override tường minh (dạng quiet_override).                                                                                                                                                                                                                                                 |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
