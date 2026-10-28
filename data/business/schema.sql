-- 原创虚构合成数据结构；无 DROP/TRUNCATE；由隔离导入器设置 search_path。

CREATE TABLE regions (
  region_id integer PRIMARY KEY,
  region_name text NOT NULL UNIQUE
);
COMMENT ON TABLE regions IS '地区维表；订单使用下单时的地区快照';
COMMENT ON COLUMN regions.region_id IS '地区主键';
COMMENT ON COLUMN regions.region_name IS '中文地区名称';
CREATE TABLE customers (
  customer_id integer PRIMARY KEY,
  customer_name text NOT NULL,
  region_id integer NOT NULL REFERENCES regions,
  customer_type text NOT NULL CHECK (customer_type IN ('individual','business'))
);
COMMENT ON TABLE customers IS '虚构客户；不包含真实姓名、电话或地址';
COMMENT ON COLUMN customers.customer_id IS '客户主键';
COMMENT ON COLUMN customers.customer_name IS '虚构中文客户展示名称';
COMMENT ON COLUMN customers.region_id IS '当前客户地区；历史统计不得替代订单地区快照';
COMMENT ON COLUMN customers.customer_type IS 'individual=个人，business=企业采购';
CREATE TABLE categories (
  category_id integer PRIMARY KEY,
  category_name text NOT NULL UNIQUE,
  storage_condition text NOT NULL
);
COMMENT ON TABLE categories IS '品类维表';
COMMENT ON COLUMN categories.category_id IS '品类主键';
COMMENT ON COLUMN categories.category_name IS '中文品类名';
COMMENT ON COLUMN categories.storage_condition IS '储运条件说明';
CREATE TABLE suppliers (
  supplier_id integer PRIMARY KEY,
  supplier_name text NOT NULL UNIQUE,
  qualification_status text NOT NULL CHECK (qualification_status IN ('approved','reviewing'))
);
COMMENT ON TABLE suppliers IS '虚构供应商；准入流程对应业务文档';
COMMENT ON COLUMN suppliers.supplier_id IS '供应商主键';
COMMENT ON COLUMN suppliers.supplier_name IS '虚构中文供应商名称';
COMMENT ON COLUMN suppliers.qualification_status IS 'approved=已准入，reviewing=审核中；只向已准入供应商采购';
CREATE TABLE products (
  product_id integer PRIMARY KEY,
  product_name text NOT NULL,
  category_id integer NOT NULL REFERENCES categories,
  supplier_id integer NOT NULL REFERENCES suppliers,
  unit text NOT NULL,
  list_price numeric(12,2) NOT NULL CHECK (list_price > 0),
  is_active boolean NOT NULL
);
COMMENT ON TABLE products IS '商品主数据；历史价格与品类以订单明细快照为准';
COMMENT ON COLUMN products.product_id IS '商品主键';
COMMENT ON COLUMN products.product_name IS '虚构中文商品名称（含规格）';
COMMENT ON COLUMN products.category_id IS '当前所属品类';
COMMENT ON COLUMN products.supplier_id IS '供应商外键';
COMMENT ON COLUMN products.unit IS '计量单位；退款数量与购买数量使用相同单位';
COMMENT ON COLUMN products.list_price IS '当前含税标价，单位元；不用于历史实付统计';
COMMENT ON COLUMN products.is_active IS '是否在售';
CREATE TABLE orders (
  order_id integer PRIMARY KEY,
  order_no text NOT NULL UNIQUE,
  customer_id integer NOT NULL REFERENCES customers,
  region_id integer NOT NULL REFERENCES regions,
  order_status text NOT NULL CHECK (order_status IN ('created','cancelled','paid','shipped','fulfilled')),
  payment_channel text NOT NULL CHECK (payment_channel IN ('wallet','bank')),
  created_at timestamptz NOT NULL,
  paid_at timestamptz ,
  promised_ship_at timestamptz ,
  shipped_at timestamptz ,
  delivered_at timestamptz ,
  paid_amount numeric(12,2) NOT NULL CHECK (paid_amount >= 0)
);
COMMENT ON TABLE orders IS '支付订单头；运费为零，实付为订单明细实付之和';
COMMENT ON COLUMN orders.order_id IS '订单主键';
COMMENT ON COLUMN orders.order_no IS '业务订单号';
COMMENT ON COLUMN orders.customer_id IS '客户外键';
COMMENT ON COLUMN orders.region_id IS '收货地区快照；运营地域口径使用此字段';
COMMENT ON COLUMN orders.order_status IS 'created=待支付，cancelled=未支付取消，paid=已支付待发货，shipped=已发货，fulfilled=已签收；退款不覆盖履约状态';
COMMENT ON COLUMN orders.payment_channel IS 'wallet=电子钱包，bank=银行卡；退款原路返回';
COMMENT ON COLUMN orders.created_at IS '订单创建时刻，非支付时刻';
COMMENT ON COLUMN orders.paid_at IS '支付成功时刻；NULL 表示未支付，不进入支付订单分母';
COMMENT ON COLUMN orders.promised_ship_at IS '承诺最晚发货时刻；本数据包为支付后24自然小时';
COMMENT ON COLUMN orders.shipped_at IS '仓库交承运方的实际发货时刻；不能替代验收时间';
COMMENT ON COLUMN orders.delivered_at IS '客户签收时刻；不能替代退款材料验收时刻';
COMMENT ON COLUMN orders.paid_amount IS '订单实付商品金额，单位元；未支付订单为0；不扣退款';
CREATE TABLE order_items (
  order_item_id integer PRIMARY KEY,
  order_id integer NOT NULL REFERENCES orders,
  product_id integer NOT NULL REFERENCES products,
  category_id integer NOT NULL REFERENCES categories,
  quantity integer NOT NULL CHECK (quantity > 0),
  unit_paid_price numeric(12,2) NOT NULL CHECK (unit_paid_price > 0),
  paid_amount numeric(12,2) NOT NULL CHECK (paid_amount >= 0)
);
COMMENT ON TABLE order_items IS '订单商品明细；一单多商品、多品类；价格及品类均为成交快照';
COMMENT ON COLUMN order_items.order_item_id IS '订单明细主键';
COMMENT ON COLUMN order_items.order_id IS '所属订单外键';
COMMENT ON COLUMN order_items.product_id IS '商品外键';
COMMENT ON COLUMN order_items.category_id IS '成交时品类快照，品类统计使用此字段';
COMMENT ON COLUMN order_items.quantity IS '购买件数';
COMMENT ON COLUMN order_items.unit_paid_price IS '优惠分摊后的每件实付价，单位元；本包无额外运费';
COMMENT ON COLUMN order_items.paid_amount IS '该行实付金额，单位元；未支付为0，支付后=件数×实付单价';
CREATE TABLE refunds (
  refund_id integer PRIMARY KEY,
  refund_no text NOT NULL UNIQUE,
  order_id integer NOT NULL REFERENCES orders,
  refund_status text NOT NULL CHECK (refund_status IN ('requested','accepted','completed','rejected','cancelled')),
  refund_kind text NOT NULL CHECK (refund_kind IN ('refund_only','return_and_refund')),
  reason_code text NOT NULL CHECK (reason_code IN ('quality','damage','wrong_item','customer_choice')),
  applied_at timestamptz NOT NULL,
  accepted_at timestamptz ,
  completed_at timestamptz ,
  payment_channel text NOT NULL CHECK (payment_channel IN ('wallet','bank')),
  requested_amount numeric(12,2) NOT NULL CHECK (requested_amount > 0),
  acceptance_note text NOT NULL
);
COMMENT ON TABLE refunds IS '退款申请与处理记录；允许同一订单多张合法退款单';
COMMENT ON COLUMN refunds.refund_id IS '退款主键';
COMMENT ON COLUMN refunds.refund_no IS '退款业务编号';
COMMENT ON COLUMN refunds.order_id IS '所属订单外键';
COMMENT ON COLUMN refunds.refund_status IS 'requested=申请待验收，accepted=已验收待到账，completed=原路退款成功，rejected=驳回，cancelled=客户撤销';
COMMENT ON COLUMN refunds.refund_kind IS 'refund_only=凭证验收后仅退款，return_and_refund=退货实物及材料验收后退款';
COMMENT ON COLUMN refunds.reason_code IS 'quality=品质问题，damage=破损，wrong_item=错发，customer_choice=客户意愿';
COMMENT ON COLUMN refunds.applied_at IS '提交退款申请时刻；用于选择适用制度版本';
COMMENT ON COLUMN refunds.accepted_at IS '退货/证据材料完整并由售后验收通过的时刻；退款到账计时起点；NULL 时不得用申请、发货、签收或更新时间替代';
COMMENT ON COLUMN refunds.completed_at IS '支付渠道确认原路退款成功时刻；仅 completed 有值；退款到账计时终点';
COMMENT ON COLUMN refunds.payment_channel IS '原支付渠道快照，须与订单一致';
COMMENT ON COLUMN refunds.requested_amount IS '申请金额=退款商品明细金额之和，单位元；完成成功时即成功退款金额';
COMMENT ON COLUMN refunds.acceptance_note IS '验收备注；历史缺失记录保留原始说明，不自动补时间';
CREATE TABLE refund_items (
  refund_item_id integer PRIMARY KEY,
  refund_id integer NOT NULL REFERENCES refunds,
  order_item_id integer NOT NULL REFERENCES order_items,
  quantity integer NOT NULL CHECK (quantity > 0),
  amount numeric(12,2) NOT NULL CHECK (amount > 0)
);
COMMENT ON TABLE refund_items IS '退款商品分配明细；成功及在途申请共同占用可退数量/金额，驳回撤销不占用';
COMMENT ON COLUMN refund_items.refund_item_id IS '退款商品明细主键';
COMMENT ON COLUMN refund_items.refund_id IS '退款单外键';
COMMENT ON COLUMN refund_items.order_item_id IS '原购买明细外键；必须属于退款头所指订单';
COMMENT ON COLUMN refund_items.quantity IS '本次申请退的件数';
COMMENT ON COLUMN refund_items.amount IS '本次分配金额，单位元；=数量×原明细实付单价';
CREATE TABLE demo_context (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  seed integer NOT NULL,
  reference_datetime timestamptz NOT NULL,
  period_start timestamptz NOT NULL,
  cutoff_exclusive timestamptz NOT NULL,
  timezone text NOT NULL CHECK (timezone='Asia/Shanghai'),
  synthetic boolean NOT NULL CHECK (synthetic)
);
COMMENT ON TABLE demo_context IS '合成数据运行元数据；只有一行，非企业业务数据';
COMMENT ON COLUMN demo_context.singleton IS '单行键，固定 true';
COMMENT ON COLUMN demo_context.seed IS '随机种子';
COMMENT ON COLUMN demo_context.reference_datetime IS '演示当前时刻；上个月以此解析';
COMMENT ON COLUMN demo_context.period_start IS '报告支付统计起点，包含';
COMMENT ON COLUMN demo_context.cutoff_exclusive IS '报告统计截止点，不包含；成功退款也必须严格早于此值';
COMMENT ON COLUMN demo_context.timezone IS '文档、数据、查询统一时区';
COMMENT ON COLUMN demo_context.synthetic IS '必须为true，全部为虚构合成资料';

ALTER TABLE order_items ADD UNIQUE(order_id, product_id);
ALTER TABLE refund_items ADD UNIQUE(refund_id, order_item_id);
ALTER TABLE orders ADD CHECK (
  created_at <= paid_at AND paid_at <= promised_ship_at
  AND paid_at <= shipped_at AND shipped_at <= delivered_at);
ALTER TABLE orders ADD CHECK (
  (paid_at IS NULL AND paid_amount=0 AND order_status IN ('created','cancelled')
   AND promised_ship_at IS NULL AND shipped_at IS NULL AND delivered_at IS NULL)
  OR (paid_at IS NOT NULL AND promised_ship_at IS NOT NULL
      AND order_status IN ('paid','shipped','fulfilled') AND paid_amount>0));
ALTER TABLE orders ADD CHECK (
  (order_status='fulfilled' AND shipped_at IS NOT NULL AND delivered_at IS NOT NULL)
  OR (order_status='shipped' AND shipped_at IS NOT NULL AND delivered_at IS NULL)
  OR (order_status IN ('paid','created','cancelled') AND shipped_at IS NULL AND delivered_at IS NULL));
ALTER TABLE refunds ADD CHECK (applied_at <= accepted_at AND accepted_at <= completed_at AND applied_at <= completed_at);
ALTER TABLE refunds ADD CHECK ((refund_status='completed') = (completed_at IS NOT NULL));
ALTER TABLE refunds ADD CHECK (refund_status <> 'accepted' OR accepted_at IS NOT NULL);
CREATE INDEX orders_scope_idx ON orders(region_id, paid_at);
CREATE INDEX order_items_category_idx ON order_items(category_id, order_id);
CREATE INDEX order_items_order_idx ON order_items(order_id);
CREATE INDEX refunds_order_idx ON refunds(order_id, completed_at);
CREATE INDEX refunds_applied_idx ON refunds(applied_at);
CREATE INDEX refund_items_original_idx ON refund_items(order_item_id);

-- Deferred global consistency guard. Demo size is small; statements run at commit.
-- Per-transaction advisory lock serializes writers even when multiple refunds target one line.
CREATE FUNCTION assert_demo_consistency() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF current_setting('demo.integrity_checked', true)='on' THEN RETURN NULL; END IF;
 IF EXISTS (SELECT 1 FROM order_items i JOIN orders o USING(order_id)
   WHERE i.paid_amount <> CASE WHEN o.paid_at IS NULL THEN 0 ELSE i.quantity*i.unit_paid_price END)
 THEN RAISE EXCEPTION 'DEMO_INTEGRITY: order item paid amount'; END IF;
 IF EXISTS (SELECT 1 FROM orders o LEFT JOIN (SELECT order_id,sum(paid_amount) s FROM order_items GROUP BY 1) i USING(order_id)
   WHERE o.paid_amount <> coalesce(i.s,0))
 THEN RAISE EXCEPTION 'DEMO_INTEGRITY: order total'; END IF;
 IF EXISTS (SELECT 1 FROM refunds r LEFT JOIN (SELECT refund_id,sum(amount) s FROM refund_items GROUP BY 1) i USING(refund_id)
   WHERE r.requested_amount <> coalesce(i.s,0))
 THEN RAISE EXCEPTION 'DEMO_INTEGRITY: refund total'; END IF;
 IF EXISTS (SELECT 1 FROM refund_items ri JOIN refunds r USING(refund_id)
   JOIN order_items i USING(order_item_id) JOIN orders o ON o.order_id=i.order_id
   WHERE r.order_id<>i.order_id OR ri.amount<>ri.quantity*i.unit_paid_price
      OR o.paid_at IS NULL OR r.applied_at<o.paid_at OR r.payment_channel<>o.payment_channel)
 THEN RAISE EXCEPTION 'DEMO_INTEGRITY: refund original purchase or channel'; END IF;
 IF EXISTS (SELECT 1 FROM refund_items ri JOIN refunds r USING(refund_id)
   JOIN order_items i USING(order_item_id)
   WHERE r.refund_status NOT IN ('rejected','cancelled')
   GROUP BY i.order_item_id, i.quantity, i.paid_amount
   HAVING sum(ri.quantity)>i.quantity OR sum(ri.amount)>i.paid_amount)
 THEN RAISE EXCEPTION 'DEMO_INTEGRITY: cumulative over-refund'; END IF;
 PERFORM set_config('demo.integrity_checked','on',true);
 RETURN NULL;
END $$;
CREATE FUNCTION mark_demo_dirty() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(610271);
 PERFORM set_config('demo.integrity_checked','off',true);
 RETURN NULL;
END $$;

CREATE TRIGGER orders_dirty BEFORE INSERT OR UPDATE OR DELETE ON orders FOR EACH STATEMENT EXECUTE FUNCTION mark_demo_dirty();
CREATE CONSTRAINT TRIGGER orders_consistency AFTER INSERT OR UPDATE OR DELETE ON orders DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION assert_demo_consistency();
CREATE TRIGGER order_items_dirty BEFORE INSERT OR UPDATE OR DELETE ON order_items FOR EACH STATEMENT EXECUTE FUNCTION mark_demo_dirty();
CREATE CONSTRAINT TRIGGER order_items_consistency AFTER INSERT OR UPDATE OR DELETE ON order_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION assert_demo_consistency();
CREATE TRIGGER refunds_dirty BEFORE INSERT OR UPDATE OR DELETE ON refunds FOR EACH STATEMENT EXECUTE FUNCTION mark_demo_dirty();
CREATE CONSTRAINT TRIGGER refunds_consistency AFTER INSERT OR UPDATE OR DELETE ON refunds DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION assert_demo_consistency();
CREATE TRIGGER refund_items_dirty BEFORE INSERT OR UPDATE OR DELETE ON refund_items FOR EACH STATEMENT EXECUTE FUNCTION mark_demo_dirty();
CREATE CONSTRAINT TRIGGER refund_items_consistency AFTER INSERT OR UPDATE OR DELETE ON refund_items DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION assert_demo_consistency();
