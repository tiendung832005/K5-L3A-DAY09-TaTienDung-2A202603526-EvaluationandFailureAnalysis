# Judge audit

Chạy: `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5` và `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có (PASS) | dùng |
| helpful | 100 | 0.382 | 1.000 | 0.292 | Không (FAIL — κ < 0.6 và R < 0.7) | loại |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 (`judge_tone`) | PASS | FAIL | Người đúng | Reply dùng *"Em đã hoàn tiền cho anh rồi nha"* — xưng "em" + "nha" quá suồng sã; sửa rubric cấm từ cảm thán suồng sã ("nha", "nhé", emoji) và bắt buộc xưng "LogiX" – "anh/chị". |
| 2 | H-017 (`judge_tone`) | PASS | FAIL | Người đúng | Reply dùng *"Dạ, bạn ơi LogiX đã hoàn 25.000đ... rồi nha."* — xưng "bạn ơi" thiếu trang trọng; cập nhật rubric bổ sung danh sách đại từ cấm ("bạn", "mình", "em"). |
| 3 | H-029 (`judge_tone`) | PASS | FAIL | Người đúng | Reply *"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."* — mang giọng ra lệnh ở vế sau nhưng judge bị đánh lừa bởi chữ "Dạ, vui lòng" đầu câu; bổ sung negative examples cho câu mệnh lệnh phủ định. |
| 4 | H-042 (`judge_tone`) | FAIL | PASS | Người đúng | Reply *"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."* — ngắn gọn, lịch sự, đủ thông tin nhưng judge phạt nhầm vì thiếu lời xin lỗi; làm rõ trong rubric rằng thông báo hoàn tiền thành công không bắt buộc xin lỗi. |
| 5 | H-081 (`judge_tone`) | FAIL | PASS | Judge đúng | Reply *"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ."* — đúng chuẩn giọng văn CSKH nhưng người gán nhãn đọc nhầm ticket nên chấm nhầm PASS/FAIL; sửa lại nhãn gốc (ground truth) trong tập audit. |
| 6 | HL-015 (`judge_helpful`) | PASS | FAIL | Người đúng | Reply *"Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ."* trong khi ledger thực tế chỉ ghi `40.000đ`; judge không có quyền truy cập ledger nên tin câu trả lời trôi chảy. |

## Kết luận
- **Tiêu chí bị loại và lý do:** Loại bỏ `judge_helpful` (`TP=7, FP=0, FN=17, TN=76`, Recall chỉ đạt `0.292` và $\kappa = 0.382$). Judge bỏ sót 17/24 ca lỗi (đặc biệt là 14 ca báo sai số tiền hoàn như HL-015, HL-016, HL-020) vì judge chỉ đọc văn bản trả lời mà không đối chiếu được với SQLite ledger, dẫn đến thiên kiến đánh giá cao các câu xin lỗi dài dòng, lịch sự nhưng sai sự thật. Các tiêu chí liên quan đến tiền bạc và phê duyệt phải chấm bằng **code grader** đối chiếu trực tiếp với ledger.
- **Rủi ro còn lại:** Judge `tone_ok` chỉ mới được hiệu chỉnh trên tập replay công khai (`judge_tone_public.csv`, $n=100$, tỉ lệ lỗi quan sát $0.280 \rightarrow$ hiệu chỉnh Rogan-Gladen $0.300$); cần thu thập thêm dữ liệu gán nhãn độc lập (held-out) từ các bản chạy thực tế để tránh overfitting rubric.