import { request } from './client'
interface Base {
  code: number
  msg?: string
}
export interface LoginInput {
  username: string
  password: string
  code: string
  uuid: string
}
export interface Captcha extends Base {
  captchaEnabled: boolean
  img: string
  uuid: string
}
export interface User {
  userId: string | number
  userName: string
  nickName: string
}
export interface UserInfo extends Base {
  user: User
  roles: string[]
  permissions: string[]
  isDefaultModifyPwd?: boolean
  isPasswordExpired?: boolean
}
export const getCaptcha = () => request<Captcha>({ url: '/captchaImage' }, false)
export const getUserInfo = () => request<UserInfo>({ url: '/getInfo' })
export const logout = () => request<Base>({ url: '/logout', method: 'POST' })
export async function login(input: LoginInput) {
  return request<Base & { token: string }>(
    {
      url: '/login',
      method: 'POST',
      data: new URLSearchParams({ ...input, username: input.username.trim() }),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    },
    false,
  )
}
