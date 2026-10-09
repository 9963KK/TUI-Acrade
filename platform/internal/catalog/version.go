package catalog

import (
	"fmt"
	"strconv"
	"strings"
)

// Version 保存解释器的主版本、次版本和补丁版本。
type Version [3]int

// ParseVersion 读取 3、3.10 或 3.10.4，缺少的版本部分补零。
func ParseVersion(text string) (Version, error) {
	var v Version
	parts := strings.Split(strings.TrimSpace(text), ".")
	if len(parts) == 0 || len(parts) > 3 {
		return v, fmt.Errorf("invalid version %q", text)
	}
	for i, part := range parts {
		n, err := strconv.Atoi(part)
		if err != nil || n < 0 {
			return v, fmt.Errorf("invalid version %q", text)
		}
		v[i] = n
	}
	return v, nil
}

func (v Version) String() string { return fmt.Sprintf("%d.%d.%d", v[0], v[1], v[2]) }

func (v Version) compare(o Version) int {
	for i := range v {
		if v[i] != o[i] {
			if v[i] < o[i] {
				return -1
			}
			return 1
		}
	}
	return 0
}

type bound struct {
	op      string
	version Version
}

// Constraint 保存逗号分隔的版本条件，例如 >=3.10,<4；零值允许任意版本。
type Constraint struct {
	text   string
	bounds []bound
}

// ParseConstraint 校验并解析版本条件。
func ParseConstraint(text string) (Constraint, error) {
	c := Constraint{text: strings.TrimSpace(text)}
	if c.text == "" {
		return c, fmt.Errorf("empty version constraint")
	}
	for _, clause := range strings.Split(c.text, ",") {
		clause = strings.TrimSpace(clause)
		op := ""
		for _, candidate := range []string{">=", "<=", "==", ">", "<"} {
			if strings.HasPrefix(clause, candidate) {
				op = candidate
				break
			}
		}
		if op == "" {
			return c, fmt.Errorf("%q must start with >=, >, <=, < or ==", clause)
		}
		version, err := ParseVersion(clause[len(op):])
		if err != nil {
			return c, err
		}
		c.bounds = append(c.bounds, bound{op, version})
	}
	return c, nil
}

// Allows 判断版本是否满足所有条件。
func (c Constraint) Allows(v Version) bool {
	for _, b := range c.bounds {
		cmp := v.compare(b.version)
		ok := map[string]bool{">=": cmp >= 0, ">": cmp > 0, "<=": cmp <= 0, "<": cmp < 0, "==": cmp == 0}[b.op]
		if !ok {
			return false
		}
	}
	return true
}

// String 返回原始版本条件，零值返回任意版本。
func (c Constraint) String() string {
	if c.text == "" {
		return "任意版本"
	}
	return c.text
}
